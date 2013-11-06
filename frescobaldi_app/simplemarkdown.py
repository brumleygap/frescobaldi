#!python
# SimpleMarkdown -- a basic markdown-like parser.
#
# Copyright (c) 2013 - 2013 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
SimpleMarkdown -- a basic markdown-like parser.

It supports different ways to iterate over the parsed text fragments and events.

It supports the following blocklevel items:

=== heading 1

== heading 2

= heading 3

plain text paragraph

* unordered list

1. ordered list

  * nested lists are possible
  
    a paragraph without bullet item

* compact item list
* item 2 (here no paragraphs will be put in the list items)

term of definition list
: definition text


```language
verbatim code
```

Block quotes are not supported

inline level:

*emphasis*

`code`

[link]
[link text]
[image:filename]

"""


from __future__ import unicode_literals

import contextlib


def chop_left(string, chars=None):
    """Return the string that string.lstrip(chars) would chop off."""
    return string[:-len(string.lstrip(chars))]

def iter_split(text, separator):
    """Yield pairs of text before and after the separator."""
    while True:
        t = text.split(separator, 2)
        if len(t) < 3:
            if text:
                yield text, ''
            break
        yield t[:2]
        text = t[2]

def iter_split2(text, separator, separator2):
    """Yield pairs of text outside and inside the separators.
    
    This can be used to parse e.g. "text with [bracketed words] in it".
    
    """
    while True:
        t = text.split(separator, 1)
        if len(t) > 1:
            t2 = t[1].split(separator2, 1)
            if len(t2) > 1:
                yield t[0], t2[0]
                text = t2[1]
                continue
        if text:
            yield text, ''
        return

def html(text):
    """Convenience function converting markdown text to HTML."""
    o = HtmlOutput()
    p = Parser()
    p.parse(text, o)
    return o.html()

def tree(text):
    """Convenience function returning the Tree object with the parsed markdown."""
    t = Tree()
    p = Parser()
    p.parse(text, t)
    return t


class Parser(object):
    """A basic Markdown-like parser.
    
    Usage:
    
    p = simplemarkdown.Parser()
    o = simplemarkdown.HtmlOutput() # or a different Output subclass instance
    text = "some markdown-formatted text"
    p.parse(text, o)
    o.html()
    
    You can also set an Output instance directly and use other parsing methods:
    
    p = simplemarkdown.Parser()
    p.output = simplemarkdown.HtmlOutput()
    p.parse_inline_text('text with *emphasized* words')
    p.output.html()
    
    """
    def __init__(self):
        self._lists = []
        self.output = Output()
    
    ##
    # block level parsing
    ##
    
    def parse(self, text, output=None):
        """Parse the text.
        
        Calls the push and pop methods on the output object, if specified.
        
        """
        self.parse_lines(text.splitlines(), output)
    
    def parse_lines(self, lines, output=None):
        """Parse text line by line.
        
        The lines may be a generator.
        Calls the push and pop methods on the output object, if specified.
        
        """
        if output is not None:
            self.output = output
        lines = iter(lines)
        para = []
        for line in lines:
            if line.lstrip().startswith('```'):
                # code
                if para:
                    self.parse_paragraph(para)
                    para = []
                indent = len(chop_left(line))
                specifier = line.lstrip('` ').rstrip() or None
                code = []
                for line in lines:
                    if line.lstrip().startswith('```'):
                        break
                    code.append(line)
                self.handle_lists(indent)
                self.output.append('code', '\n'.join(code), specifier)
            elif not line or line.isspace():
                if para:
                    self.parse_paragraph(para)
                    para = []
            else:
                para.append(line)
        if para:
            self.parse_paragraph(para)
    
    def parse_paragraph(self, lines):
        """Parse a list of one or more lines without blank lines in between.
        
        Dispatches the lines to handle headings, lists or plain text paragraphs.
        
        """
        indent = len(chop_left(lines[0]))
        if lines[0].lstrip().startswith('='):
            self.handle_lists(indent)
            self.parse_heading(lines)
        elif self.is_ul_item(lines[0]):
            self.handle_lists(indent, 'unorderedlist')
            self.parse_ul(lines)
        elif self.is_ol_item(lines[0]):
            self.handle_lists(indent, 'orderedlist')
            self.parse_ol(lines)
        elif self.is_dl_item(lines):
            self.handle_lists(indent, 'definitionlist')
            self.parse_dl(lines)
        elif not self.special_paragraph(lines):
            self.handle_lists(indent)
            with self.output('paragraph'):
                self.parse_inline_lines(lines)
    
    def special_paragraph(self, lines):
        """Called when a paragraph is not a heading or a list item.
        
        If this method returns True, it is assumed to have handled the contents.
        This can be used to extend the paragraph-level parser to understand more
        types of paragraphs.
        
        The default implementation does nothing and returns None, which causes
        the lines to be assumed to be a normal paragraph.
        
        """
        pass
    
    def is_ul_item(self, line):
        """Return True if the line is a unordered list prefix ("*")."""
        try:
            prefix, line = line.split(None, 1)
            return prefix == '*'
        except ValueError:
            return False

    def is_ol_item(self, line):
        """Return True if the line is a ordered list prefix (number period)."""
        try:
            prefix, line = line.split(None, 1)
            return prefix.endswith('.') and prefix[:-1].isdigit()
        except ValueError:
            return False
    
    def is_dl_item(self, lines):
        """Return True lines are a description list item."""
        return len(lines) > 1 and lines[1].lstrip().startswith(': ')
    
    def parse_heading(self, lines):
        """Parse a header text."""
        prefix = chop_left(lines[0], '= ')
        heading_type = 4 - min(prefix.count('='), 3)
        lines[0] = lines[0].strip('= ')
        with self.output('heading', heading_type):
            self.parse_inline_lines(lines)
    
    def parse_ol(self, lines):
        """Parse ordered lists.
        
        Every line of the supplied group of lines is checked for a number,
        if they are separate items, no paragraph tags are put around the list
        items.
        
        """
        # split in list items
        items = self.split_list_items(lines, self.is_ol_item)
        paragraph_item = len(items) == 1
        for item in items:
            with self.output('orderedlist_item'):
                if paragraph_item:
                    with self.output('paragraph'):
                        self.parse_inline_lines(item)
                else:
                    self.parse_inline_lines(item)
            
    def parse_ul(self, lines):
        """Parse unordered lists.
        
        Every line of the supplied group of lines is checked for an asterisk,
        if they are separate items, no paragraph tags are put around the list
        items.
        
        """
        items = self.split_list_items(lines, self.is_ul_item)
        paragraph_item = len(items) == 1
        for item in items:
            with self.output('unorderedlist_item'):
                if paragraph_item:
                    with self.output('paragraph'):
                        self.parse_inline_lines(item)
                else:
                    self.parse_inline_lines(item)
    
    def split_list_items(self, lines, pred):
        """Returns lists of lines that each represent a list item.
        
        The pred function should return true for a line that has an item prefix.
        
        """
        items = []
        item = []
        for line in lines:
            if pred(line):
                if item:
                    items.append(item)
                item = [line.split(None, 1)[1]]
            else:
                item.append(line)
        if item:
            items.append(item)
        return items
        
    def parse_dl(self, lines):
        """Parse a definition list item."""
        definition = lines[0]
        lines[1] = lines[1].split(':', 1)[1]
        with self.output('definitionlist_item'):
            with self.output('definitionlist_item_term'):
                self.parse_inline_lines([definition])
            with self.output('definitionlist_item_definition'):
                self.parse_inline_lines(lines[1:])
    
    def handle_lists(self, indent, list_type=None):
        """Close ongoing lists or start new lists if needed.
        
        If given, list_type should be 'orderedlist', 'unorderedlist', or
        'definitionlist'.
        
        """
        if list_type and (not self._lists or self._lists[-1][1] < indent):
            self._lists.append((list_type, indent))
            self.output.push(list_type)
        else:
            while self._lists:
                if self._lists[-1][1] > indent:
                    self.output.pop()
                    self._lists.pop()
                    continue
                elif self._lists[-1][1] == indent and self._lists[-1][0] != list_type:
                    self.output.pop()
                    self._lists.pop()
                    if list_type:
                        self._lists.append((list_type, indent))
                        self.output.push(list_type)
                break
            
    ##
    # inline level parsing
    ##
    
    def parse_inline_lines(self, lines):
        """Parse plain text lines with possibly inline markup.
        
        This implementation strip()s the lines, joins them with a newline
        and calls parse_inline_text() with the text string.
        
        """
        self.parse_inline_text('\n'.join(line.strip() for line in lines))
        
    def parse_inline_text(self, text):
        """Parse a continuous text block with possibly inline markup."""
        with self.output('inline'):
            self.parse_inline_links(text)
    
    def parse_inline_links(self, text):
        """Parse text for links."""
        # TODO escape [ and ] ?
        for nolink, link in iter_split2(text, '[', ']'):
            if nolink:
                self.parse_inline_emphasis(nolink)
            if link:
                link = link.split(None, 1)
                if len(link) == 1:
                    url = text = link[0]
                else:
                    url, text = link
                with self.output('link', url):
                    self.parse_inline_emphasis(text)
        
    def parse_inline_emphasis(self, text):
        """Parse a piece of text for emphasis formatting."""
        for normal, emph in iter_split(text, '*'):
            if normal:
                self.parse_inline_code(normal)
            if emph:
                with self.output('inline_emphasis'):
                    self.parse_inline_code(emph)
        
    def parse_inline_code(self, text):
        """Parse a piece of text for code formatting."""
        for text, code in iter_split(text, '`'):
            if text:
                self.output.append('inline_text', text)
            if code:
                self.output.append('inline_code', code)


class Output(object):
    """Base class for output handler objects.
    
    You should inherit from this class and implement the push() and pop() methods.
    
    """
    @contextlib.contextmanager
    def __call__(self, name, *args):
        """Context manager to push a new node and perform code, pop on exit."""
        self.push(name, *args)
        try:
            yield
        finally:
            self.pop()
    
    def append(self, name, *args):
        """Append a new node to the current node."""
        self.push(name, *args)
        self.pop()
    
    def push(self, name, *args):
        """Append a new node to the current node and make it current."""
        pass
    
    def pop(self):
        """Make the current node's parent the current node."""
        pass


class Tree(Output):
    """An Output that represents the tree structure of the parsed text."""
    
    class Node(list):
        def __new__(cls, name, *args):
            n = list.__new__(cls)
            n.name = name
            n.args = args
            return n

        def __init__(self, name, *args):
            list.__init__(self)
        
        def __nonzero__(self):
            return True
        
        def __repr__(self):
            return '<Node "{0}" {1} [{2}]>'.format(self.name, self.args, len(self))

        def __str__(self):
            return "{0} {1}".format(self.name, self.args)
    
    
    def __init__(self):
        self._root = self.Node('root')
        self._cursor = [self._root]
    
    # build the tree
    def push(self, name, *args):
        """Append a Node to the current node, and make that the current Node."""
        node = self.Node(name, *args)
        self._cursor[-1].append(node)
        self._cursor.append(node)
    
    def pop(self):
        """End the current Node and go back to the parent node."""
        if len(self._cursor) > 1:
            self._cursor.pop()
    
    # query the tree
    def root(self):
        """Return the root (which is a plain Python list)."""
        return self._root
    
    def dump(self, node=None, indent_start=0, indent_string='  '):
        """Show the node or the entire tree in a pretty-printed string."""
        def dump(n, indent):
            yield '{0}{1}'.format(indent_string * indent, n)
            for n1 in n:
                for s in dump(n1, indent + 1):
                    yield s
        nodes = [node] if node is not None else self._root
        return '\n'.join(s for n in nodes for s in dump(n, indent_start))

    def copy(self, output, node=None):
        """Copy the tree to the other output instance.
        
        If node is not specified, the entire tree is copied.
        
        """
        if node in (None, self._root):
            for n in self._root:
                self.copy(output, n)
        else:
            with output(node.name, *node.args):
                for n in node:
                    self.copy(output, n)
    
    def find(self, path, node=None):
        """Iter over the elements described by path.
        
        Currently this just yields all elements with the specified name.
        
        If node is not given, the entire tree is searched.
        
        """
        if node is None:
            node = self._root
        for n in node:
            if n.name == path:
                yield n
            for n1 in self.find(path, n):
                yield n1
    
    def iter_tree(self, node=None):
        """Iter over all elements of the tree.
        
        Every 'yield' is a list from the node's child up to the element itself.
        If node is not given, the root node is used.
        
        """
        def iter_tree(node, cursor=[]):
            for n in node:
                l = cursor + [n]
                yield l
                for l in iter_tree(n, l):
                    yield l
        return iter_tree(node or self._root)
    
    def iter_tree_find(self, path, node=None):
        """Iter over the elements described by path.
        
        Currently this just yields all elements with the specified name.
        Every 'yield' is a list from the node's child up to the element itself.
        
        If node is not given, the entire tree is searched.
        
        """
        def iter_tree_find(node, cursor=[]):
            for n in node:
                l = cursor + [n]
                if n.name == path:
                    yield l
                for l in iter_tree_find(n, l):
                    yield l
        return iter_tree_find(node or self._root)
    
    def html(self, node=None):
        """Convenience method to return HTML text from the specified node.
        
        If node is not given, the entire document is returned as HTML text.
        This method uses the HtmlOutput class to create the HTML text.
        
        """
        o = HtmlOutput()
        self.copy(o, node)
        return o.html()


class HtmlOutput(Output):
    """Converts output to HTML."""
    def __init__(self):
        self._html = []
        self._tags = []
    
    def push(self, name, *args):
        self._tags.append((name, args))
        getattr(self, name + '_start')(*args)
        
    def pop(self):
        name, args = self._tags.pop()
        getattr(self, name + '_end')(*args)
        
    def html(self):
        return ''.join(self._html)
    
    def html_escape(self, text):
        """Escapes &, < and >."""
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    def tag(self, name, attrs=None):
        """Add a tag. Use a name like '/p' to write a close tag.
        
        attrs may be a dictionary of attributes.
        
        """
        if attrs:
            a = ''.join(' {0}="{1}"'.format(
                name, self.html_escape(value).replace('"', '&quot;'))
                for name, value in attrs.items())
        else:
            a = ''
        self._html.append('<{0}{1}>'.format(name, a))
    
    def nl(self):
        """Add a newline."""
        self._html.append('\n')
    
    def text(self, text):
        self._html.append(self.html_escape(text))
    
    ##
    # block level handlers
    ##

    def code_start(self, code, specifier=None):
        self.tag('code')
        self.tag('pre')
        self.text(code)
    
    def code_end(self, code, specifier=None):
        self.tag('/pre')
        self.tag('/code')
        self.nl()
    
    def heading_start(self, heading_type):
        self.tag('h{0}'.format(heading_type))
    
    def heading_end(self, heading_type):
        self.tag('/h{0}'.format(heading_type))
        self.nl()
        
    def paragraph_start(self):
        self.tag('p')
    
    def paragraph_end(self):
        self.tag('/p')
        self.nl()
    
    def orderedlist_start(self):
        self.tag('ol')
        self.nl()
    
    def orderedlist_item_start(self):
        self.tag('li')
    
    def orderedlist_item_end(self):
        self.tag('/li')
        self.nl()
    
    def orderedlist_end(self):
        self.tag('/ol')
        self.nl()
    
    def unorderedlist_start(self):
        self.tag('ul')
        self.nl()
    
    def unorderedlist_item_start(self):
        self.tag('li')
    
    def unorderedlist_item_end(self):
        self.tag('/li')
        self.nl()

    def unorderedlist_end(self):
        self.tag('/ul')
        self.nl()
    
    def definitionlist_start(self):
        self.tag('dl')
        self.nl()
        
    def definitionlist_item_term_start(self):
        self.tag('dt')
        
    def definitionlist_item_term_end(self):
        self.tag('/dt')
        self.nl()
        
    def definitionlist_item_definition_start(self):
        self.tag('dd')
        
    def definitionlist_item_definition_end(self):
        self.tag('/dd')
        self.nl()
        
    def definitionlist_item_start(self):
        pass
        
    def definitionlist_item_end(self):
        pass
        
    def definitionlist_end(self):
        self.tag('/dl')
        self.nl()

    ##
    # inline handlers
    ##

    def inline_start(self):
        """Called when a block of inline text is parsed."""
        pass
        
    def inline_end(self):
        """Called at the end of parsing a block of inline text.""" 
        pass
    
    def inline_code_start(self, text):
        self.tag('code')
        self.text(text)
    
    def inline_code_end(self, text):
        self.tag('/code')
    
    def inline_emphasis_start(self):
        self.tag('em')
    
    def inline_emphasis_end(self):
        self.tag('/em')
    
    def link_start(self, url):
        self.tag('a', {'href': url})
    
    def link_end(self, url):
        self.tag('/a')
    
    def inline_text_start(self, text):
        self.text(text)

    def inline_text_end(self, text):
        pass

