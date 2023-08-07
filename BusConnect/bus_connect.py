import os
import sys
import re

class BUS_CONNECT:

    apb_inf = [
      'penable',
      'psel',
      'pwrite',
      'pready',
      'paddr',
      'pwdata',
      'prdata',
      'pslverr'
    ]

    def __init__ (self, vfile, top, param = {}):
        self.file = vfile
        self.top  = top
        self.param_override = param
        port_txt, param_txt = self.parse_file(self.file)
        if port_txt == '':
            raise Exception ("Failed to find port '%s' in file '%s'" % (top, vfile))
        self.parse_inf (port_txt, param_txt)

    def parse_file (self, file):
        text = open(file, 'r').read()
        res  = re.findall(r'module\s+(%s)\s*(#\s*\(.+?\)\s*)?\((.*?)\)\s*;' % self.top, text, re.MULTILINE | re.DOTALL)
        if len(res) > 0:
            param_txt = res[0][1]
            port_txt  = res[0][2]
        else:
            port_txt  = ''
            param_txt = ''
        return port_txt, param_txt

    def parse_inf (self, port_txt, param_txt):
        self.params   = []
        self.port     = []
        self.parse_port (port_txt, param_txt)

    def print_port (self):
        for sig in self.port:
            if sig['width'] == 1:
                vect = ''
            else:
                vect = f"[{sig['start'] + sig['width'] - 1}:{sig['start']}]"
            print (f"{sig['dir']:10s} {sig['name']:20s} {vect}")

    def expand_params (self, text, prefix = ''):
        for each in self.params:
            if prefix:
                text = text.replace(each, '%s%s' % (prefix, each))
            else:
                text = text.replace(each, str(self.params[each]))
        return text

    def parse_port (self, port_txt, param_txt, expand = True):
        port   = []
        params = {}
        for line in param_txt.splitlines():
            match = re.match('\s*(parameter|localparam)(?:.*)?\s+(\w+)\s*=\s*(\d+)[\s,]?.*', line)
            if match:
                params[match.group(2)] = match.group(3)
        params.update(self.param_override)
        self.params = params

        for line in port_txt.splitlines():
            #output wire logic                              WVALID_OB,
            match = re.match('\s*(input|output|inout)\s+((wire|reg)\s+)?(logic\s+)?(\[.*\]\s+)?(\w+).*', line)
            if match:
                name = match.group(6)
                if match.group(5) is None:
                    start = 0
                    end   = 0
                    vect  = ''
                else:
                    remain = match.group(5)
                    pos1  = remain.find(':')
                    pos2  = remain.find(']')
                    expr1 = self.expand_params (remain[1:pos1])
                    start = int(eval(expr1))
                    expr2 = self.expand_params (remain[pos1+1:pos2])
                    end   = int(eval(expr2))
                    vect  = remain[1:pos2].strip()
                    if self.top == 'axi_xbar':
                        prefix = 'CST_'
                    else:
                        prefix = ''
                    vect  = self.expand_params (vect, prefix)

                sig = {}
                port.append(sig)
                sig['dir']   = match.group(1)
                sig['start'] = end
                sig['width'] = start - end + 1
                sig['name']  = name
                sig['vect']  = vect

        self.port = port

def signal_map (name, mapping, pattern):
    parts = pattern.split(':')
    pos   = parts[0].find('$xxx')
    head1 = parts[0][:pos]
    tail1 = parts[0][pos+4:]
    pos   = parts[1].find('$xxx')
    head2 = parts[1][:pos]
    tail2 = parts[1][pos+4:]

    if name in mapping:
        wire = mapping[name]
    elif name.startswith(head1) and name.endswith(tail1):
        pos1 = len(head1)
        pos2 = len(name) - len(tail1)
        name = name[pos1:pos2]
        wire = head2 + name + tail2
    else:
        wire = ''
        name = ''
    return wire.lower(), name.lower()

def port_map (port, mapping, patterns, keep_param = False):
    wire_lines = []
    conn_lines = []
    port_lines = []
    for sig in port:
        wire = ''
        for pat in patterns:
            wire, base = signal_map(sig['name'], mapping, f'{pat}:{patterns[pat]}')
            if wire:
                break
        if wire == '':
            #raise Exception ("Unknown mapping to %s !" % sig['name'])
            continue
        if base in mapping:
            continue
        if sig['width'] == 1:
            vect = ''
        else:
            vect = f"[{sig['start'] + sig['width'] - 1}:{sig['start']}]"
        if keep_param:
            vect = '%40s' % f"[{sig['vect']}]"
        wire_lines.append ('    wire %10s    %s;' % (vect, wire))
        conn_lines.append ('    .%s (%s),' % (sig['name'], wire))
        if sig['vect'] != '':
            vect_str = '[%s]' % sig['vect']
        else:
            vect_str = ''
        port_lines.append ('    %-10s wire %-40s %s,' % (sig['dir'], vect_str, sig['name'].lower()))

    return port_lines, wire_lines, conn_lines

def wire_assign (port, mapping, patterns, is_master = True):

    keep_param = False

    wire_lines = []
    conn_lines = []
    port_lines = []
    for sig in port:
        wire = ''
        for pat in patterns:
            wire, base = signal_map(sig['name'], mapping, f'{pat}:{patterns[pat]}')
            if wire:
                break
        if wire == '':
            #raise Exception ("Unknown mapping to %s !" % sig['name'])
            continue
        if base in mapping:
            continue
        if sig['width'] == 1:
            vect = ''
        else:
            vect = f"[{sig['start'] + sig['width'] - 1}:{sig['start']}]"
        if keep_param:
            vect = '%40s' % f"[{sig['vect']}]"

        if sig['dir'] == 'output':
            pdir = 1
        elif sig['dir'] == 'input':
            pdir = 0
        else:
            raise Exception ('Unsupported direction %s !' % sig['dir'])

        if is_master:
            pdir = 1 - pdir

        if pdir:
            wire_b = sig['name']
            wire_a = wire
        else:
            wire_a = sig['name']
            wire_b = wire

        wire_lines.append ('    assign %20s =  %s;' % (wire_a, wire_b))

    return wire_lines

def xbar_expand_line (line, params):
    line = line.replace ('CST_NM', '1')
    line = line.replace ('CST_NS', '1')
    line = line.replace ('CST_C_AXI_ID_WIDTH',   str(params['C_AXI_ID_WIDTH']))
    line = line.replace ('CST_C_AXI_ADDR_WIDTH', str(params['C_AXI_ADDR_WIDTH']))
    line = line.replace ('CST_C_AXI_DATA_WIDTH', str(params['C_AXI_DATA_WIDTH']))
    return line

def exclude_line (lines, exclude):
    result = []
    for each in lines:
        skip = False
        for exc in exclude:
            if exc in each:
                skip = True
                break
        if not skip:
            result.append(each)
    return result

def conn_xbar_comp (name, port, dev, comp_pat):
    mapping = {}
    exclude = []
    if ';' in comp_pat:
        pattern = {}
        for each in comp_pat.split(';'):
            if each[0] == '!':
                exclude.append(each[1:])
                continue
            pattern[each] = '%s_axi_$xxx' % port
    else:
        pattern = { comp_pat : '%s_axi_$xxx' % port }
    port_lines, wire_lines, conn_lines = port_map (dev.port, mapping, pattern)
    conn_lines = exclude_line (conn_lines, exclude)
    text = '`define  AXI_%s_%s_XBAR_PORT_MAP \\\n' % (name.upper(),port.upper()) + ' \\\n'.join(conn_lines)
    print ('%s\n\n' % text.rstrip(','))
    print ('')

def port_map_xbar (port, mapping, params, nm_inf_msk, ns_inf_msk):
    nm = params['NM']
    ns = params['NS']

    nm_wire_msk = ((1 << nm) - 1) & ~nm_inf_msk
    ns_wire_msk = ((1 << ns) - 1) & ~ns_inf_msk

    wire_lines = []
    conn_lines = []
    port_lines = []
    s_map = []
    m_map = []
    for i in range (nm):
        s_map.append('s%d_axi_$xxx' % i)
    for i in range (ns):
        m_map.append('m%d_axi_$xxx' % i)

    patterns = {
      'S_AXI_$xxx' : '{%s}' % ', '.join(s_map[::-1]),
      'M_AXI_$xxx' : '{%s}' % ', '.join(m_map[::-1]),
    }

    for sig in port:
        if sig['name'] in mapping:
            continue

        for pat in patterns:
            wire, base = signal_map(sig['name'], mapping, f'{pat}:{patterns[pat]}')
            if wire:
                wire = patterns[pat].replace('$xxx', base)
                break
        if wire == '':
            raise Exception ("Unknown mapping to %s !" % sig['name'])
        if sig['width'] == 1:
            vect = ' ' * 40
        else:
            vect_str = xbar_expand_line (sig['vect'], params)
            vect = '%40s' % f"[{vect_str}]"

        wire_list = []
        if pat[0] == 'M':
            for i in range(16):
                if (1<<i) & ns_wire_msk:
                    wire_list.append("m%d_axi_%s" % (i, base))
        elif pat[0] == 'S':
            for i in range(16):
                if (1<<i) & nm_wire_msk:
                    wire_list.append("s%d_axi_%s" % (i, base))
        if len(wire_list):
            wire_lines.append ('    wire %s    %s;' % (vect, ','.join (wire_list)))

        conn_lines.append ('    .%s (%s),' % (sig['name'], wire))

        vect = xbar_expand_line (sig['vect'], params)
        fline = '    %-10s wire %-40s %s,' % (sig['dir'], '[%s]' % vect, sig['name'].lower())
        port_lines.append (fline)

    return port_lines, wire_lines, conn_lines


def gen_xbar (axi_xbar, nm, ns, nm_inf_msk = 0xffffffff, ns_inf_msk = 0xffffffff):

    mapping = {
      'S_AXI_ACLK'    : 'clk_i',
      'S_AXI_ARESETN' : 'rst_n_i'
    }

    pattern = {
      'S_AXI_$xxx' : 's_axi_$xxx',
      'M_AXI_$xxx' : 'm_axi_$xxx',
    }

    port_lines, wire_lines, conn_lines = port_map_xbar (axi_xbar.port, mapping, axi_xbar.params, nm_inf_msk, ns_inf_msk)

    for key in axi_xbar.params.keys():
        text = '`define  CST_%-20s %s' %  (key, axi_xbar.params[key])
        print ('%s' % text)
    print ('\n\n')

    text = '`define  AXI_XBAR_PORT_MAP  \\\n' + ' \\\n'.join(conn_lines)
    print ('%s\n\n' % text.rstrip(','))

    new_wire_lines = wire_lines
    text = '`define  AXI_XBAR_PORT_WIRE \\\n' + ' \\\n'.join(new_wire_lines)
    print ('%s\n\n' % text.rstrip(';'))

    new_port_lines = []
    for i in range(nm):
        if ((1 << i) & nm_inf_msk) == 0:
            continue
        for line in port_lines:
            if ' s_axi_' not in line:
                continue
            line = line.replace (' s_axi_', ' s%d_axi_' % i)
            new_port_lines.append(line)

    for i in range(ns):
        if ((1 << i) & ns_inf_msk) == 0:
            continue
        for line in port_lines:
            if ' m_axi_' not in line:
                continue
            line = line.replace (' m_axi_', ' m%d_axi_' % i)
            new_port_lines.append(line)

    text = '`define  AXI_XBAR_PORT_INF \\\n' + ' \\\n'.join(new_port_lines)
    print ('%s\n\n' % text.rstrip(','))

def conn_comp (name, dev, pattern):
    mapping = { }
    port_lines, wire_lines, conn_lines = port_map (dev.port, mapping, pattern)

    if name.endswith('_PORT_MAP'):
        lines = conn_lines
    elif name.endswith('_PORT_WIRE'):
        lines = wire_lines
    else:
        raise Exception ("Unknown connections for port !")
    text = '`define  %s \\\n' % (name.upper()) + ' \\\n'.join(lines)
    print ('%s\n\n' % text.rstrip(',').rstrip(';'))
    print ('')

def gen_apb_mux (ns, apb_mux, apb_dev):

    mapping = { }
    params  = {"SLAVE_NUM" : ns}

    lines = []
    text = '`define  APB_NS  %d' % ns
    lines.append(text)
    text = '`define  APB_DW  %s' % apb_mux.params['SLAVE_DW']
    lines.append(text)
    text = '`define  APB_AW  %s' % apb_mux.params['SLAVE_AW']
    lines.append(text)

    print ('\n'.join(lines) + '\n')

    wire_lines = []
    pattern = {'$xxx' : 'apb_s0_$xxx'}
    port_lines, wire_lines, conn_lines = port_map (apb_dev.port, mapping, pattern)
    slave_lines = []
    for i in range(ns):
        for line in wire_lines:
            line = line.replace('apb_s0_', 'apb_m%s_' % i)
            slave_lines.append (line)
    text = '`define  APB_MUX_PORT_WIRE \\\n' + ' \\\n'.join(wire_lines + slave_lines)
    print ('%s\n\n' % text.rstrip('\\').rstrip(';'))

    pattern = {'SLV_$xxx' : 'apb_m_$xxx'}
    port_lines, wire_lines, conn_lines = port_map (apb_mux.port, mapping, pattern)

    slave_conn = []
    for line in conn_lines:
        pos1 = line.find('(')
        pos2 = line.find(')')
        sig = line[pos1+1:pos2]
        sig_fmt = sig.replace('apb_m_', 'apb_m%d_')
        slave_dev = ['%s' % (sig_fmt % (ns-i-1)) for i in range(ns)]
        line = line.replace(sig, '{ %s }' % ', '.join(slave_dev))
        slave_conn.append (line)

    pattern = {'MST_$xxx' : 'apb_s0_$xxx'}
    port_lines, wire_lines, conn_lines = port_map (apb_mux.port, mapping, pattern)
    text = '`define  APB_MUX_PORT_MAP \\\n' + ' \\\n'.join(conn_lines + slave_conn)
    print ('%s\n\n' % text.rstrip('\\').rstrip(','))

    misc_line = []
    for i in range(ns):
        for sig in ['penable', 'pwrite', 'paddr', 'pwdata']:
            misc_line.append ('    assign  apb_m%d_%s = apb_s0_%s;' % (i, sig, sig))

    text = '`define  APB_MUX_PORT_MISC \\\n' + ' \\\n'.join(misc_line)
    print ('%s\n\n' % text.rstrip('\\').rstrip(';'))

    if 0:

        new_wires = """
        wire     [31:0]    mem_wdata;
        wire      [3:0]    mem_wstrb;
        wire               mem_instr;
        wire               mem_valid;
        """
        wire_lines.extend (new_wires.splitlines()[1:-1])
        text = '`define  LBUS_MUX_PORT_WIRE \\\n' + ' \\\n'.join(wire_lines)
        print ('%s\n\n' % text.rstrip('\\').rstrip(';'))


        port_lines, wire_lines, conn_lines = port_map (lbus_mux.port, mapping, pattern)
        text = '`define  LBUS_MUX_PORT_MAP \\\n' + ' \\\n'.join(conn_lines)
        print ('%s\n\n' % text.rstrip(','))

        pattern = {
            'mem_re$xxx' : 'mem_re$xxx_slv[$i]',
            'mem_rd$xxx' : 'mem_rd$xxx_slv[$v]',
            'mem_en$xxx' : 'mem_en$xxxs[$i]',
            'mem_$xxx'   : 'mem_$xxx',
        }
        port_lines, wire_lines, conn_lines = port_map (lbus_dev.port, mapping, pattern)

        for i in range(ns):
            lines = []
            for line in conn_lines:
              line = line.replace('$v', '%d +: %d' % (i * params['SLAVE_AW'], params['SLAVE_AW']))
              line = line.replace('$i', str(i))
              if 'mem_instr' in line:
                  continue
              lines.append(line)
            text = '`define  LBUS_S%d_DEV_PORT_MAP \\\n' % i + ' \\\n'.join(lines)
            print ('%s\n\n' % text.rstrip(','))

        print ('')


def gen_lbus_mux (ns, lbus_mux, lbus_dev):

    lbus_mux_extra = """
        output wire [SLAVE_AW-1:0]    lbus_wdata,
        output wire [SLAVE_AW/8-1:0]  lbus_wstrb,
        output wire                   lbus_instr,
        output wire                   lbus_valid,
    """

    mapping = { }
    params  = {"SLAVE_NUM" : ns, 'SLAVE_AW' : 32}

    text = '`define  LBUS_NS  %d\n' % ns
    print (text)
    text = '`define  LBUS_AW  %d\n' % params['SLAVE_AW']
    print (text)

    pattern = {'lbus_$xxx' : 'mem_$xxx'}
    port_lines, wire_lines, conn_lines = port_map (lbus_mux.port, mapping, pattern)

    port_lines, wire_lines, conn_lines = port_map (lbus_mux.port, mapping, pattern)

    new_wires = """
    wire     [31:0]    mem_wdata;
    wire      [3:0]    mem_wstrb;
    wire               mem_instr;
    wire               mem_valid;
    """
    wire_lines.extend (new_wires.splitlines()[1:-1])
    text = '`define  LBUS_MUX_PORT_WIRE \\\n' + ' \\\n'.join(wire_lines)
    print ('%s\n\n' % text.rstrip('\\').rstrip(';'))


    port_lines, wire_lines, conn_lines = port_map (lbus_mux.port, mapping, pattern)
    text = '`define  LBUS_MUX_PORT_MAP \\\n' + ' \\\n'.join(conn_lines)
    print ('%s\n\n' % text.rstrip(','))

    pattern = {
        'mem_re$xxx' : 'mem_re$xxx_slv[$i]',
        'mem_rd$xxx' : 'mem_rd$xxx_slv[$v]',
        'mem_en$xxx' : 'mem_en$xxxs[$i]',
        'mem_$xxx'   : 'mem_$xxx',
    }
    port_lines, wire_lines, conn_lines = port_map (lbus_dev.port, mapping, pattern)

    for i in range(ns):
        lines = []
        for line in conn_lines:
          line = line.replace('$v', '%d +: %d' % (i * params['SLAVE_AW'], params['SLAVE_AW']))
          line = line.replace('$i', str(i))
          if 'mem_instr' in line:
              continue
          lines.append(line)
        text = '`define  LBUS_S%d_DEV_PORT_MAP \\\n' % i + ' \\\n'.join(lines)
        print ('%s\n\n' % text.rstrip(','))

    print ('')


def usage():
    print ("Usage:\n  %s subcmd args" % os.path.basename(__file__))
    print ("    axi_xbar AXI_N MAXI_NS")
    print ("        AXI_NM :  Number of master devices to connect to XBAR slave interfaces")
    print ("        AXI_NS :  Number of slave devices to connect to XBAR master interfaces")
    print ("    lbus_mux LBUS_NS")
    print ("        LBUS_NS:  Number of slave devices to connect to LBUS mux")
    return

def main ():
    if len(sys.argv) < 2:
        usage ()
        return

    top_dir = os.path.join(os.path.dirname(__file__) , '../../hw/src')
    rtl_dir = os.path.join(os.path.dirname(__file__) , '../../rtl')

    if sys.argv[1] == 'lbus_mux':
        ns = int(sys.argv[2])

        for each in range(ns):
            text = '`define  LBUS_S%d  %d' % (each, each)
            print (text)
        print ('')

        params = {
          "SLAVE_NUM" : ns,
        }
        file_top = (top_dir + r'/lbus_mux/lbus_mux.v', 'lbus_mux')
        lbus_mux = BUS_CONNECT (file_top[0], file_top[1], params)
        file_top = (top_dir + r'/lbus_timer/lbus_timer.v', 'lbus_timer')
        lbus_timer = BUS_CONNECT (file_top[0], file_top[1])
        gen_lbus_mux (ns, lbus_mux, lbus_timer)


    elif sys.argv[1] == 'apb_mux':
        ns = int(sys.argv[2])
        params = {
          "SLAVE_NUM" : ns,
        }
        file_top = (top_dir + r'/apb_mux/apb_dev.v', 'apb_dev')
        apb_dev = BUS_CONNECT (file_top[0], file_top[1])
        file_top = (top_dir + r'/apb_mux/apb_mux.v', 'apb_mux')
        apb_mux = BUS_CONNECT (file_top[0], file_top[1])
        gen_apb_mux (ns, apb_mux, apb_dev)


    elif sys.argv[1] == 'axi_xbar':
        nm = int(sys.argv[2])
        ns = int(sys.argv[3])

        #
        # S0:  CPU
        # S1:  EXT test inf to connect a external AXI master
        #
        # M0:  Sys memory
        # M1:  Locla bus (UART, timer)
        # M2:  Ram
        # M3:  AXI to APB bridge to connect a external APB slave
        # M4:  EXT test inf to connect a external AXI slave
        params = {
          "NM"                   : nm,
          "NS"                   : ns,
        }
        file_top = (top_dir + r'/axi_xbar/axi_xbar.v', 'axi_xbar')
        axi_xbar = BUS_CONNECT (file_top[0], file_top[1], params)

        file_top = (top_dir + r'/axi_ram/axi_ram.v', 'axi_ram')
        axi_ram = BUS_CONNECT (file_top[0], file_top[1], params)

        file_top   = (top_dir + r'/lbus_axil/lbus_axil.v', 'lbus_axil')
        lbus_axil  = BUS_CONNECT (file_top[0], file_top[1], params)

        file_top = (top_dir + r'/axil_apb/axil_apb.v', 'axil_apb')
        axil_apb = BUS_CONNECT (file_top[0], file_top[1])

        file_top = (top_dir + r'/spi_axi_lbus/spi_dbg_axi_lbus.v', 'spi_dbg_axi_lbus')
        spi_dbg = BUS_CONNECT (file_top[0], file_top[1])

        # 1: interface signal  0: internal wire
        nm_inf_mask = 0x0
        ns_inf_mask = 0x0
        gen_xbar (axi_xbar, nm, ns, nm_inf_mask, ns_inf_mask)

        comp_pat = 'axi_$xxx_i;axi_$xxx_o'
        conn_xbar_comp ('LBUS', 's1', lbus_axil,  comp_pat)

        comp_pat = 'mem_$xxx_i;mem_$xxx_o'
        conn_xbar_comp ('DBG', 's2', spi_dbg,  comp_pat)

        comp_pat = 's_axi_$xxx'
        conn_xbar_comp ('MEM',  'm1', axi_ram,  comp_pat)

        comp_pat = 'S_AXI_$xxx;!S_AXI_ACLK;!S_AXI_ARESETN'
        conn_xbar_comp ('APB', 'm2', axil_apb, comp_pat)

        if 0:
            file_top = (top_dir + r'/axi_axil/axi_axil.v', 'axi_axil')
            axi_axil = BUS_CONNECT (file_top[0], file_top[1])
            comp_pat = 'S_AXI_$xxx;!S_AXI_ACLK;!S_AXI_ARESETN'
            conn_xbar_comp ('AXIL',  'm0', axi_axil,  comp_pat)
            patterns = {'M_AXI_$xxx' : 'axil_m0_$xxx'}
            conn_comp ('AXIL_DEV_PORT_WIRE', axi_axil, patterns)
            patterns = {'M_AXI_$xxx' : 'axil_m0_$xxx'}
            conn_comp ('AXIL_DEV_PORT_MAP', axi_axil, patterns)

            file_top = (top_dir + r'/axil_dma/axil_dma.v', 'axil_dma')
            axil_dma = BUS_CONNECT (file_top[0], file_top[1])
            patterns = {'S_AXIL_$xxx' : 'axil_m0_$xxx'}
            conn_comp ('AXIL_DMA_PORT_MAP', axil_dma, patterns)
            comp_pat = 'M_AXI_$xxx;!S_AXI_ACLK;!S_AXI_ARESETN'
            conn_xbar_comp ('DMA',  's0', axil_dma,  comp_pat)
        else:
            file_top = (top_dir + r'/axil_dma/axil_dma.v', 'axil_dma')
            axil_dma = BUS_CONNECT (file_top[0], file_top[1])
            comp_pat = 'S_AXIL_$xxx;!S_AXI_ACLK;!S_AXI_ARESETN'
            conn_xbar_comp ('AXIL',  'm0', axil_dma,  comp_pat)
            comp_pat = 'M_AXI_$xxx;!S_AXI_ACLK;!S_AXI_ARESETN'
            conn_xbar_comp ('DMA',  's0', axil_dma,  comp_pat)

        patterns = {'M_APB_$xxx' : 'apb_s0_$xxx'}
        conn_comp ('AXI_APB_DEV_PORT_WIRE', axil_apb, patterns)
        conn_comp ('AXI_APB_DEV_PORT_MAP',  axil_apb, patterns)


    elif sys.argv[1] == 'axi_wire':
            file_top = (sys.argv[2], sys.argv[3])
            mod_inf  = BUS_CONNECT (file_top[0], file_top[1])
            mapping = {}
            pattern = {
                        'S_$xxx' : 's0_$xxx'
                      }
            wire_lines = wire_assign (mod_inf.port, mapping, pattern)

            print ('\n'.join(wire_lines))
            #mod_inf.print_port()


    return

main ()
