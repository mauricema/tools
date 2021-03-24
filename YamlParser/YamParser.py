## @ YamlParser.py
#
# copyright (c) 2021, intel corporation. all rights reserved.<BR>
# SPDX-license-identifier: BSD-2-clause-patent
#
##

import sys
import os
import re
import string
from   collections import OrderedDict

class CFG_YAML():
    TEMPLATE = 'template'
    CONFIGS  = 'configs'
    VARIABLE = 'variable'

    class DEF_TEMPLATE(string.Template):
        idpattern = '\([_A-Z][_A-Z0-9]*\)|[_A-Z][_A-Z0-9]*'

    def __init__ (self):
        self.log_line        = False
        self.allow_template  = False
        self.cfg_tree        = None
        self.tmp_tree        = None
        self.var_dict        = None
        self.def_dict        = {}
        self.yaml_path       = ''
        self.lines           = []
        self.full_lines      = []
        self.index           = 0
        self.re_expand  = re.compile (r'(.+:\s+|\s*\-\s*)!expand\s+\{\s*(\w+_TMPL)\s*:\s*\[(.+)]\s*\}')
        self.re_include = re.compile (r'(.+:\s+|\s*\-\s*)!include\s+(.+)')

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
        return next((i for i, c in enumerate(line) if not c.isspace()), len(line))

    @staticmethod
    def substitue_args (text, arg_dict):
        for arg in arg_dict:
            text = text.replace ('$' + arg, arg_dict[arg])
        return text

    @staticmethod
    def dprint (*args):
        pass

    def process_include (self, line, insert = True):
        match = self.re_include.match (line)
        if not match:
            raise Exception ("Invalid !include format '%s' !" % line.strip())

        prefix  = match.group(1)
        include = match.group(2)
        if prefix.strip() == '-':
            prefix = ''
            adjust = 0
        else:
            adjust = 2

        include = strip_quote (include)
        request = CFG_YAML.count_indent (line) + adjust

        if self.log_line:
            # remove the include line itself
            del  self.full_lines[-1]

        inc_path = os.path.join (self.yaml_path, include)
        if not os.path.exists(inc_path):
            # try relative path to project root
            try_path = os.path.join(os.path.dirname (os.path.realpath(__file__)), "../..", include)
            if os.path.exists(try_path):
                inc_path = try_path
            else:
                raise Exception ("ERROR: Cannot open file '%s'." % inc_path)

        lines = CFG_YAML.read_lines (inc_path)

        current   = 0
        same_line = False
        for idx, each in enumerate (lines):
            start = each.lstrip()
            if start == '' or start[0] == '#':
                continue

            if start[0] == '>':
                # append the content directly at the same line
                same_line = True

            start   = idx
            current = CFG_YAML.count_indent (each)
            break

        lines = lines[start+1:] if same_line else lines[start:]
        leading = ''
        if same_line:
            request = len(prefix)
            leading = '>'

        lines = [prefix + '%s\n' % leading] + [' ' * request + i[current:] for i in lines]
        if insert:
            self.lines = lines + self.lines

        return lines

    def process_expand (self, line):
        match = self.re_expand.match(line)
        if not match:
            raise Exception ("Invalid !expand format '%s' !" % line.strip())
        lines      = []
        prefix     = match.group(1)
        temp_name  = match.group(2)
        args       = match.group(3)

        if prefix.strip() == '-':
            indent = 0
        else:
            indent = 2
        lines      = self.process_expand_template (temp_name, prefix, args, indent)
        self.lines = lines + self.lines


    def process_expand_template (self, temp_name, prefix, args, indent = 2):
        # expand text with arg substitution
        if temp_name not in self.tmp_tree:
            raise Exception ("Could not find template '%s' !" % temp_name)
        parts = args.split(',')
        parts = [i.strip() for i in parts]
        num = len(parts)
        arg_dict = dict(zip( ['(%d)' % (i + 1) for i in range(num)], parts))
        str_data = self.tmp_tree[temp_name]
        text = CFG_YAML.DEF_TEMPLATE(str_data).safe_substitute(self.def_dict)
        text = CFG_YAML.substitue_args (text, arg_dict)
        target  = CFG_YAML.count_indent (prefix) + indent
        current = CFG_YAML.count_indent (text)
        padding = target * ' '
        if indent == 0:
            leading = []
        else:
            leading = [prefix + '\n']
        text = leading + [(padding + i + '\n')[current:] for i in text.splitlines()]
        return text


    def load_file (self, yaml_file):
        self.index  = 0
        self.lines = CFG_YAML.read_lines (yaml_file)


    def peek_line (self):
        if len(self.lines) == 0:
            return None
        else:
            return self.lines[0]


    def put_line (self, line):
        self.lines.insert (0, line)
        if self.log_line:
            del self.full_lines[-1]


    def get_line (self):
        if len(self.lines) == 0:
            return None
        else:
            line = self.lines.pop(0)
            if self.log_line:
                self.full_lines.append (line.rstrip())
            return line


    def get_multiple_line (self, indent):
        text   = ''
        newind = indent + 1
        while True:
            line   = self.peek_line ()
            if line is None:
                break
            sline = line.strip()
            if sline != '':
                newind = CFG_YAML.count_indent(line)
                if newind <= indent:
                    break
            self.get_line ()
            if sline != '':
                text = text + line
        return text


    def traverse_cfg_tree (self, handler):
        def _traverse_cfg_tree (root, level = 0):
            # config structure
            for key in root:
                if type(root[key]) is OrderedDict:
                    level += 1
                    handler (key, root[key], level)
                    _traverse_cfg_tree (root[key], level)
                    level -= 1
        _traverse_cfg_tree (self.cfg_tree)


    def count (self):
        def _count (name, cfgs, level):
            num[0] += 1
        num = [0]
        self.traverse_cfg_tree (_count)
        return  num[0]


    def parse (self, parent_name = '', curr = None, level = 0):
        child = None
        last_indent = None
        temp_chk = {}

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
                self.put_line (' ' * indent + curr_line)

            if curr_line.endswith (': >'):
                # multiline marker
                old_count = len(self.full_lines)
                line = self.get_multiple_line (indent)
                if self.log_line and not self.allow_template and '!include ' in line:
                    # expand include in template
                    new_lines = []
                    lines = line.splitlines()
                    for idx, each in enumerate(lines):
                        if '!include ' in each:
                            new_line = ''.join(self.process_include (each, False))
                            new_lines.append(new_line)
                        else:
                            new_lines.append(each)
                    self.full_lines = self.full_lines[:old_count] + new_lines
                curr_line = curr_line  + line

            if indent > last_indent:
                # child nodes
                if child is None:
                    raise Exception ('Unexpected format at line: %s' % (curr_line))

                level += 1
                self.parse (key, child, level)
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

            if curr is None:
                curr = OrderedDict()

            if indent < last_indent:
                return curr

            marker1 = curr_line[0]
            marker2 = curr_line[-1]
            start = 1 if marker1 == '-' else 0
            pos = curr_line.find(': ')
            if pos > 0:
                child = None
                key = curr_line[start:pos].strip()
                if curr_line[pos + 2] == '>':
                    curr[key] = curr_line[pos + 3:]
                else:
                    # XXXX: !include / !expand
                    if '!include ' in curr_line:
                        self.process_include (line)
                    elif '!expand ' in curr_line:
                        if self.allow_template and not self.log_line:
                            self.process_expand (line)
                    else:
                        value_str = curr_line[pos + 2:].strip()
                        curr[key] = value_str
                        if self.log_line and value_str[0] == '{':
                            # expand {FILE: xxxx} format in the log line
                            if value_str[1:].rstrip().startswith('FILE:'):
                                value_bytes = expand_file_value (self.yaml_path, value_str)
                                value_str = bytes_to_bracket_str (value_bytes)
                                self.full_lines[-1] = line[:indent] + curr_line[:pos + 2] + value_str

            elif marker2 == ':':
                child = OrderedDict()
                key = curr_line[start:-1].strip()
                if key == '$ACTION':
                    # special virtual nodes, rename to ensure unique key
                    key = '$ACTION_%04X' % self.index
                    self.index += 1
                if key in curr:
                    if key not in temp_chk:
                        # check for duplicated keys at same level
                        temp_chk[key] = 1
                    else:
                        raise Exception ("Duplicated item '%s:%s' found !" % (parent_name, key))

                curr[key] = child
                if self.var_dict is None and key == CFG_YAML.VARIABLE:
                    self.var_dict = child
                if self.tmp_tree is None and key == CFG_YAML.TEMPLATE:
                    self.tmp_tree = child
                    if self.var_dict:
                        for each in self.var_dict:
                            txt = self.var_dict[each]
                            if type(txt) is str:
                                self.def_dict['(%s)' % each] = txt
                if self.tmp_tree and key == CFG_YAML.CONFIGS:
                    # apply template for the main configs
                    self.allow_template = True
            else:
                child = None
                # - !include cfg_opt.yaml
                if '!include ' in curr_line:
                    self.process_include (line)

        return curr


    def load_yaml (self, opt_file):
        self.var_dict  = None
        self.yaml_path = os.path.dirname (opt_file)
        self.load_file (opt_file)
        yaml_tree     = self.parse ()
        self.tmp_tree = yaml_tree[CFG_YAML.TEMPLATE]
        self.cfg_tree = yaml_tree[CFG_YAML.CONFIGS]
        return self.cfg_tree


    def expand_yaml (self, opt_file):
        self.log_line = True
        self.load_yaml (opt_file)
        self.log_line = False
        text = '\n'.join (self.full_lines)
        self.full_lines = []
        return text


    def traverse_cfg_tree (self, handler):
        def _traverse_cfg_tree (root, level = 0):
            # config structure
            for key in root:
                if type(root[key]) is OrderedDict:
                    level += 1
                    handler (key, root[key], level)
                    _traverse_cfg_tree (root[key], level)
                    level -= 1
        _traverse_cfg_tree (self.cfg_tree)


    def print_cfgs(self, root = None, short = True, print_level = 256):
        def _print_cfgs (name, cfgs, level):
            if name.startswith('$'):
                return
            indent = '  ' * level
            print ('%s%s' % (indent, name))
            for each in cfgs:
                if not isinstance(cfgs[each], OrderedDict):
                    value = cfgs[each].strip()
                    print ('  %s%-15s: %s' % (indent, each, value))

        self.traverse_cfg_tree (_print_cfgs)


def main():
    cfg_file = sys.argv[1]
    cfg_yaml = CFG_YAML()
    cfg_tree = cfg_yaml.load_yaml (cfg_file)
    cfg_yaml.print_cfgs (cfg_tree)


if __name__ == '__main__':
    sys.exit(main())

