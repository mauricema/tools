## @ uc_conv.py
#
# copyright (c) 2021, intel corporation. all rights reserved.<BR>
# SPDX-license-identifier: BSD-2-clause-patent
#
##

import os
import re
import sys
import struct

gStrTbl = [
    "Header Version",
    "Update Revision",
    "Date",
    "Processor Signature",
    "Checksum",
    "Loader Revision",
    "Processor Flags",
    "Data Size (excluding headers)",
    "Total Size (including headers)",
    "Reserved",
    "Reserved",
    "Reserved"
]

gExtList   = ['BIN', 'MCB', 'PDB', 'INC', 'H', 'DTS', 'TXT']
gMcuData   = []
gMcuRemain = 0


def Bytes2Value (bytes):
	return reduce(lambda x,y: (x<<8)|y,  bytes[::-1] )

def Value2Bytes (value, length):
	return [(value>>(i*8) & 0xff) for i in range(length)]

def Usage():
    print ("Usage: \n\tpython UcodeConv.py Inputfile(%s) Outputfile [Flags]\n" % '|'.join(gExtList))
    print ("\tFlags:")
    print ("\t\tb: Use byte instead of dword for H, TXT file.")

def RemoveComment(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ""
        else:
            return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)

def ParseBin(filepath):
    global   gMcuData
    gMcuData = []
    flen = os.path.getsize(filepath)
    fin = open (filepath, "rb")
    for i in range((flen + 3) // 4):
      dword = fin.read(4)
      sz    = len(dword)
      while sz < 4:
        dword = dword + chr(0)
        sz += 1
      data  = struct.unpack('<I', dword)
      gMcuData.append (data[0])
    fin.close()

def GenerateBin(filepath, flags):
    global   gMcuData
    global   gMcuRemain
    fout = open (filepath, "wb")
    for each in gMcuData[:-1]:
      fout.write(struct.pack("<I", each))
    if gMcuRemain > 0:
      Len = gMcuRemain
    else:
      Len = 4
    fout.write (bytearray(Value2Bytes(gMcuData[-1], Len)))
    fout.close()

def ParseInc(filepath):
    global   gMcuData
    fin   = open (filepath, "r")
    lines = fin.readlines()
    fin.close()
    cnt = 0;
    for each in lines:
      if each.startswith(';'):
        continue
      if each.startswith('/*'):
        continue
      # dd 000000000h ; Reserved
      match = re.match("\s*(dd|DD)\s+([a-fA-F0-9]+)h", each)
      if not match:
        match = re.match("\s*(\.long)\s+0x([a-fA-F0-9]+)", each)
        if not match:
          continue
      data = int(match.group(2), 16)
      gMcuData.append (data)

def ParseTxt(filepath):
    global   gMcuData
    global   gMcuRemain
    fin   = open (filepath, "r")
    lines = fin.readlines()
    fin.close()
    cnt  = 0;
    data = 0;
    for each in lines:
      hexs = re.split('\s|\-', each.strip())
      if len(hexs[0]) > 2:
        hexs = hexs[1:]
      for h in hexs:
        if len(h) == 2:
          data = data + (int(h, 16) << (cnt * 8))
          cnt += 1
          if cnt == 4:
            gMcuData.append (data)
            data = 0
            cnt  = 0
        else:
          break

    if cnt != 0:
      gMcuData.append (data)
      gMcuRemain = cnt

def GenerateInc(filepath, flags):
    global gMcuData
    cnt  = 0
    line = ""
    fout = open(filepath, "w")
    if 'g' in flags:
      fout.write("/* External header */\n")
    else:
      fout.write("; External header\n")
    for each in gMcuData:
      if 'g' in flags:
        line = ".long 0x%08x" % each
      else:
        line = "dd 0%08xh" % each
      if cnt < 12:
        if 'g' in flags:
          line = line + " /* %s */" % gStrTbl[cnt]
        else:
          line = line + "; %s" % gStrTbl[cnt]
      line = line + "\n"
      if cnt == 11:
        if 'g' in flags:
          line = line + "/* Data */\n"
        else:
          line = line + "; Data\n"
      cnt = cnt + 1
      fout.write(line)
    fout.close()

def ParseH(filepath):
    global   gMcuData
    fin   = open (filepath, "r")
    text  = fin.read()
    fin.close()
    text = RemoveComment(text).split('\n')
    unit = 0
    cnt  = 0
    data = 0
    for line in text:
      words = line.split(',')
      for each in words:
        match = re.match("\s*0x([a-fA-F0-9]+)\s*", each)
        if match:
          hex = match.group(1)
          if len(hex) > 8:
              hex = hex [-8:]
          if unit == 0:
            unit = (len(hex) + 1) & 0x0E
          data = data + (int(hex, 16) << ((unit * 4) & 0x1F))
          cnt  = cnt + unit
          if cnt == 8:
            gMcuData.append (data)
            cnt  = 0
            data = 0

def GenerateH(filepath, flags):
    global gMcuData
    cnt  = 0
    line = ""
    fout = open(filepath, "w")
    for each in gMcuData:
      if 'b' in flags:
        line = line + "0x%02x, 0x%02x, 0x%02x, 0x%02x, " % (each & 0xff, (each>>8) & 0xff, (each>>16) & 0xff, (each>>24) & 0xff)
      else:
        line = line + "0x%08x, " % each
      cnt = cnt + 1
      if (cnt & 3) == 0:
        fout.write(line + "\n")
        line = ""
    if line:
      fout.write(line + "\n")
    fout.close()

def GenerateDts(filepath, flags):
    global gMcuData
    cnt  = 0
    line = "  "
    fout = open(filepath, "w")
    for each in gMcuData:
      each = struct.unpack("<I", struct.pack(">I", each))[0]
      line = line + "0x%08x " % each
      cnt = cnt + 1
      if (cnt & 3) == 0:
        fout.write(line + "\n")
        line = "  "
    fout.close()

def Main():
    #
    # Parse the options and args
    #
    if len(sys.argv) < 3 or len(sys.argv) > 4:
      print ("Not enough argumetns!")
      Usage ()
      return -1

    if len(sys.argv) == 4:
      flags = sys.argv[3]
    else:
      flags = ''

    fileName, fileExt = os.path.splitext(sys.argv[1])
    normExt = fileExt[1:].upper()
    if normExt in ['BIN', 'PDB', 'MCB']:
      ParseBin (sys.argv[1])
    elif normExt == 'INC':
      ParseInc (sys.argv[1])
    elif normExt == 'H':
      ParseH (sys.argv[1])
    elif normExt == 'TXT':
      ParseTxt (sys.argv[1])
    else:
      print ("Unsupported input file extension!")
      return -3

    fileName, fileExt = os.path.splitext(sys.argv[2])
    if normExt == fileExt[1:].upper():
      print ("Input and output has same file extension!")
      return -4

    normExt = fileExt[1:].upper()
    if normExt   == 'BIN' or normExt == 'PDB':
      GenerateBin (sys.argv[2], flags)
    elif normExt == 'INC':
      GenerateInc (sys.argv[2], flags)
    elif normExt == 'H':
      GenerateH (sys.argv[2], flags)
    elif normExt == 'DTS':
      GenerateDts (sys.argv[2], flags)
    else:
      print ("Unsupported output file extension!")
      return -3

    print ("OK!")


if __name__ == '__main__':
    sys.exit(Main())

