import re

def Struct2Ctype (text):

    if text == "":
        return

    type_dict = {
      "UINT8"  : "c_uint8",
      "UINT16" : "c_uint16",
      "UINT32" : "c_uint32",
      "UINT64" : "c_uint64",
      "INT8"   : "c_int8",
      "INT16"  : "c_int16",
      "INT32"  : "c_int32",
      "INT64"  : "c_int64",
      "CHAR8"  : "c_char",
      "CHAR8"  : "c_wchar",
      "VOID"   : "c_void"
    }

    result = []
    state  = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue

        if state == 0:
            if parts[-1].startswith('{'):
                outputs = []
                outputs.append ('class UNKNOWN (Structure):')
                outputs.append ('  _pack_   = 1')
                outputs.append ('  _fields_ = [')
                state = 1

        elif state == 1:

            if parts[0].startswith('}'):
                struct_name = parts[1][:-1]
                outputs[0] = ('class %s (Structure):' % struct_name)
                outputs.append ('  ]')
                result.append ('\n'.join(outputs))
                state = 0

            elif parts[-1].endswith(';'):
                ftype = parts[0]
                fname = parts[1][:-1].strip()
                if ftype in type_dict.keys():
                    ftype = type_dict[ftype]
                if fname.startswith('*'):
                    fname = fname.lstrip('*')
                    if ftype in type_dict.keys():
                        ftype = ftype + '_p'
                match = re.match('.+:\s*(\d+)\s*;', ' '.join(parts[1:]))
                if match:
                    bit_field = int(match.group(1))
                else:
                    bit_field = 0

                dims = []
                parts = fname.split('[')
                if len(parts) > 1:
                    for each in parts:
                        if each.endswith(']'):
                            if each[:-1].strip() == '':
                                num = 0
                            else:
                                num = int(each[:-1], 0)
                            dims.append (num)
                    fname = parts[0]
                    for each in dims[::-1]:
                        ftype = 'ARRAY(%s, %d)' % (ftype, each)

                fname = "'%s'" % fname
                if bit_field:
                    field = "    (%-20s , %s, %d)," % (fname, ftype, bit_field)
                else:
                    field = "    (%-20s , %s)," % (fname, ftype)
                outputs.append (field)

    return result


if __name__ == '__main__':
    fp = open ('test.h', 'r')
    txt = fp.read()
    fp.close ()

    out = Struct2Ctype (txt)
    for each in out:
        print (each + '\n')



