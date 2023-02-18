## @ RegParser.py
#
# Copyright (c) 2021, Intel Corporation. All rights reserved.<BR>
# SPDX-license-identifier: BSD-2-clause-patent
#
##

import sys
import os
import re
import string
import time
from   collections import OrderedDict

class CFG_YAML():

    def __init__ (self):
        self.index = 0
        self.lines = []
        self.cfg_tree = OrderedDict()

    @staticmethod
    def read_lines (file):
        if not os.path.exists(file):
            test_file = os.path.basename(file)
            if os.path.exists(test_file):
                file = test_file
        fi = open (file, 'r')
        lines = fi.readlines ()
        fi.close ()
        return lines

    @staticmethod
    def count_indent (line):
        indent = len(line[:-len(line.lstrip())])
        #indent = next((i for i, c in enumerate(line) if not c.isspace()), len(line))
        if line[indent:].startswith('- '):
            indent = indent + 2 + CFG_YAML.count_indent(line[indent+2:])
        return indent

    def load_file (self, yaml_file):
        self.index = 0
        self.lines = CFG_YAML.read_lines (yaml_file)

    def load_yaml (self, opt_file):
        self.yaml_path = os.path.dirname (opt_file)
        self.load_file (opt_file)
        self.cfg_tree = self.parse ()

    def peek_line (self):
        if len(self.lines) == 0:
            return None
        else:
            return self.lines[0]

    def put_line (self, line):
        self.lines.insert (0, line)

    def get_line (self):
        if len(self.lines) == 0:
            return None
        else:
            line = self.lines.pop(0)
            return line

    def get_multiple_quote_line (self, quote_char):
        text_line = []
        while True:
            line   = self.peek_line ()
            if line is None:
                break
            sline = line.strip()
            self.get_line ()
            if sline:
                start = 1 if sline.startswith('\\') else 0
                end   = len(sline) if not sline.endswith('\\') else -1
                text_line.append (sline[start:end])
                if sline.endswith(quote_char):
                    break
        text = ''.join(text_line)
        return text

    def parse (self, curr_dict = None, level = 0):
        child = None
        last_indent = None
        curr_list = None
        
        while True:

            line = self.get_line ()
            if line is None:
                break

            curr_line = line.strip()
            if curr_line == '' or curr_line[0] == '#':
                continue

            indent  = CFG_YAML.count_indent(line)
            if last_indent is None:
                last_indent = indent

            if indent != last_indent:
                # outside of current block,  put the line back to queue
                self.put_line (line)

            if indent > last_indent:
                # child nodes
                if child is None:
                    raise Exception ('Unexpected format at line: %s' % (curr_line))

                level += 1
                self.parse (child, level)
                level -= 1

                line = self.peek_line ()
                if line is not None:
                    curr_line = line.strip()
                    indent  = CFG_YAML.count_indent(line)
                    if indent >= last_indent:
                        # consume the line
                        self.get_line ()
                else:
                    # end of file
                    indent = -1

            if curr_dict is None:
                curr_dict = OrderedDict()

            if indent < last_indent:
                break

            if curr_line.startswith('- '):
                curr_line = curr_line[2:].lstrip()
                child = OrderedDict()
                if curr_list is None:
                    curr_list = list()
                    curr_dict['$LIST'] = curr_list
                curr_list.append(child)
                curr_dict = child

            if curr_line[-1] == ':':
                child     = OrderedDict()
                key       = curr_line[:-1].strip()
                curr_dict[key] = child
            else:
                pos = curr_line.find(': ')
                if pos > 0:
                    key       = curr_line[:pos].strip()
                    value_str = curr_line[pos + 2:].strip()
                    if value_str[0] in ['"', "'"]:
                        if value_str[-1] == value_str[0]:
                            value_str = value_str[1:-1]
                        else:
                            value_str = value_str[:-1] + self.get_multiple_quote_line (value_str[0])
                    curr_dict[key] = value_str

        if curr_list is None:
            return curr_dict
        else:
            return curr_list


    def traverse_cfg_tree (self, handler):
        def _traverse_cfg_tree (parent, level = 0):
            if type(parent) is OrderedDict:
                for key in parent:
                    if key != '$LIST':
                        handler (key, parent[key], level)
                    if type(parent[key]) in [OrderedDict, list]:
                        level += 1
                        _traverse_cfg_tree (parent[key], level)
                        level -= 1
            elif type(parent) is list:
                for each in parent:
                    if type(each) in [OrderedDict]:
                        handler ('$LIST', each, level)
                        _traverse_cfg_tree (each, level)

        _traverse_cfg_tree (self.cfg_tree)


    def print_cfgs(self):

        def _print_cfgs (name, cfgs, level):
            indent = '  ' * level
            if isinstance(cfgs, OrderedDict):
                if name == '$LIST':
                    gbl_sts['sts'] = 1
                else:
                    print ('%s%s:' % (indent, name))
            else:
                if gbl_sts['sts']:
                    gbl_sts['sts'] = 0
                    indent = indent[2:]
                    name = '- ' + name
                print ('%s%s: %s' % (indent, name, cfgs))

        gbl_sts = {'sts' : 0}
        self.traverse_cfg_tree (_print_cfgs)

    def test (self):
        for key in self.cfg_tree:
            if key.startswith('$'):
                continue

            for each in self.cfg_tree[key]['views']['$LIST']:
                if 'fields' not in each:
                    continue

                fields = []
                width  = 0
                for field in  each['fields']['$LIST']:
                    if 'inheritsFrom' in field:
                        name = field['inheritsFrom'].split('.')[-1]
                        field['name'] = name
                    if 'name' not in field:
                        continue
                    if 'reset' in field:
                        reset = field['reset']
                    else:
                        reset = '0'
                    fields.append((field['name'], int(field['width']), reset))
                    width += int(field['width'])

                print ('%s (%d)' % (key, width))
                for name, width, reset in fields:
                    print ('  %s:%d %s' % (name, width, reset))


def main():
    cfg_file = sys.argv[1]

    cfg_yaml = CFG_YAML()
    cfg_yaml.load_yaml (cfg_file)

    cfg_yaml.print_cfgs ()


if __name__ == '__main__':
    sys.exit(main())
