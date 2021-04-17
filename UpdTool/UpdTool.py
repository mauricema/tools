## @ UpdTool.py
#
# Copyright (c) 2021, Intel Corporation. All rights reserved.<BR>
# SPDX-license-identifier: BSD-2-clause-patent
#
##

import os
import re
import sys
import struct
import argparse

def value_to_bytes(value, length, unit=1):
    bitlen = unit * 8
    return [(value >> (i * bitlen) & ((1 << bitlen) - 1))
            for i in range(length)]

def bytes_to_value (bytes):
    return int.from_bytes (bytes, 'little')

class UpdTool():
    def __init__(self, h_file, fsp_ver=21):
        self.upds = []
        self.fsp = ''
        self.parse_h(h_file)

        if fsp_ver <= 21:
            upd_arch_hdr_len = [0x20, 0x40, 0x20]
        else:
            upd_arch_hdr_len = [0x40, 0x40, 0x40]

        # For FSP 2.1
        if self.fsp == 'M':
            self.fsp_upd_hdr_len = upd_arch_hdr_len[1]
        elif self.fsp == 'S':
            self.fsp_upd_hdr_len = upd_arch_hdr_len[2]
        elif self.fsp == 'T':
            self.fsp_upd_hdr_len = upd_arch_hdr_len[0]
        else:
            raise Exception('Cannot detect FSP component type !')

    def print_upd(self):
        lastoff = self.fsp_upd_hdr_len
        for each in self.upds:
            unit = each['size'] // each['count']
            lastoff = each['offset'] + each['size']
            if 'value' in each:
                value = bytes_to_value(each['value'])
                val_list = value_to_bytes(value, each['count'], unit)
                fmt = '0x%%0%dx' % (unit * 2)
                valstr = ', '.join([fmt % x for x in val_list])
                if each['count'] > 1:
                    valstr = '{ %s }' % valstr
            else:
                valstr = '?'
            print ("@0x%04X (#%-3d)  %-40s = %s" % (
                each['offset'], each['size'], each['name'], valstr))
            next = each['offset'] + each['size']

    def compare_upd_val_str (self, each):
        unit = each['size'] // each['count']
        if 'value' in each:
            value = bytes_to_value(each['value'])
            val_list = value_to_bytes(value, each['count'], unit)
            fmt = '0x%%0%dx' % (unit * 2)
            valstr = ', '.join([fmt % x for x in val_list])
            if each['count'] > 1:
                valstr = '{ %s }' % valstr
        else:
            valstr = '?'
        return valstr

    def compare_upd(self, upds):
        if len(self.upds) != len(upds):
            raise Exception ('Two set of UPDs have mismatched length !')

        lastoff = self.fsp_upd_hdr_len
        for idx, each in enumerate(self.upds):
            each2    = upds[idx]
            val_str1 = self.compare_upd_val_str (each)
            val_str2 = self.compare_upd_val_str (each2)
            if val_str1 != val_str2:
                print ("%-40s = %s;" % (
                  '  Fsp%sConfig->%s' % (self.fsp, each['name']), val_str1))

    def load_bin (self, bins):
        bin_len = len(bins)
        upd_len = self.fsp_upd_hdr_len + sum([x['size'] for x in self.upds])
        if bin_len != upd_len:
            raise Exception("Binary size 0x%x does not match UPD definition size 0x%x!" % (bin_len, upd_len))
        #print (hex(upd_len))
        found = False
        for each in self.upds:
            each['value'] = bins[each['offset']:each['offset'] + each['size']]
            if each['name'] == 'UpdTerminator':
                found = True
                if bytes_to_value (each['value']) != 0x55aa:
                    raise Exception("Incorrect UPD Terminator value !")

        if not found:
            raise Exception("Cannot find UPD Terminator !")

    def parse_txt (self, txt_file):
        fin   = open (txt_file, "r")
        lines = fin.readlines()
        fin.close()
        bins = bytearray()
        for each in lines:
          hexs = re.split('\s|\-', each.strip())
          if len(hexs[0]) > 2:
            hexs = hexs[1:]
          for h in hexs:
            if h.startswith('0x'):
              h = h[2:]
            if len(h) == 2:
              data = int(h, 16)
              bins.append (data)
            else:
              break
        return bins


    def convert_txt_to_bin (self, txt_file, bin_file):
        bins = self.parse_txt (txt_file)
        fo = open (bin_file, 'wb')
        fo.write (bins)
        fo.close ()

    def load_txt_file (self, txt_file):
        bins = self.parse_txt (txt_file)
        self.load_bin(bins)

    def load_bin_file (self, bin_file):
        fd1 = open(bin_file, 'rb')
        bins = bytearray(fd1.read())
        fd1.close()
        self.load_bin(bins)

    def parse_h (self, h_file):
        fd1 = open(h_file)
        lines = fd1.readlines()
        fd1.close()

        idx         = 0
        oldoffset   = -1
        offset      = 0
        find_offset = 0
        find_end    = 0
        next        = 0
        self.fsp    = ''
        self.upds   = []

        for line in lines:
            # Find CName
            if '__FSPSUPD_H__' in line:
                self.fsp = 'S'
            elif '__FSPMUPD_H__' in line:
                self.fsp = 'M'
            elif '__FSPTUPD_H__' in line:
                self.fsp = 'T'

            # Parse UPD field
            match = re.match('^  UINT(\d+)(\s*)(\w*)', line)
            if not match:
                match = re.match('^  VOID(\*)(\s*)(\w*)', line)

            if match:
                if find_offset != 0 and find_end != 0:
                    upd = {}
                    if match.group(1) == '*':
                        byte_len = 32 // 8
                    else:
                        byte_len = int(match.group(1)) // 8
                    upd['name']   = match.group(3)
                    upd['count']  = 1
                    upd['unitsz'] = byte_len
                    match2 = re.search('\[(\d+)\]', line)
                    if match2:
                        upd['count'] = int(match2.group(1))
                    upd['size']   = byte_len * upd['count']
                    upd['offset'] = int(find_offset, 16)
                    if next and (upd['offset'] != next):
                        raise Exception ('Error at Name:%s Offset:0x%X' % (upd['name'], upd['offset']))
                    else:
                        next = upd['offset'] + upd['size']
                    self.upds.append(upd)
                find_end = 0
                find_offset = 0

            # Find **/
            match = re.search('(\*\*/)', line)
            if match:
                if find_offset != 0:
                    find_end = 1

            # Find offset
            match = re.search('(^/\*\* Offset )(0x[0-9A-F]{4})', line)
            if match:
                find_offset = match.group(2)
            continue

        # sort UPD by offset
        self.upds.sort(key=lambda r:r['offset'])


def display_upd(args):
    upd_tool1 = UpdTool (args.upd_header_file)
    upd_tool2 = UpdTool (args.upd_header_file)

    file = args.upd_dump_file1
    if file:
        if file.endswith('.txt'):
            upd_tool1.load_txt_file (file)
        elif file.endswith('.bin'):
            upd_tool1.load_bin_file (file)

    file = args.upd_dump_file2
    if file:
        if file.endswith('.txt'):
            upd_tool2.load_txt_file (file)
        elif file.endswith('.bin'):
            upd_tool2.load_bin_file (file)

    if file:
        # diff two set of UPDs
        upd_tool1.compare_upd (upd_tool2.upds)
    else:
        # decode current UPD
        upd_tool1.print_upd()


def main():
    parser = argparse.ArgumentParser()

    # Command for display
    parser.add_argument('-c',
                        dest='upd_header_file',
                        type=str,
                        required=True,
                        help='UPD FSP C Header File. EX: FspmUpd.h, FspsUpd.h')
    parser.add_argument(
        '-i',
        dest='upd_dump_file1',
        type=str,
        required = True,
        help='FSP UPD value dump file 1, either HEX text or binary file.')

    parser.add_argument(
        '-j',
        dest='upd_dump_file2',
        type=str,
        default = '',
        help='FSP UPD values dump file 2, either HEX text or binary file. '
             'If provided, the tool will compare it with first set of UPD values.')

    args = parser.parse_args()
    display_upd(args)


if __name__ == '__main__':
    sys.exit(main())
