"""
Methods for accessing and reading droplet generator logs.
"""

from qtools.lib.storage import QLBFileSource
from qtools.model import DropletGeneratorRun
import re, os
from datetime import datetime

KEYVAL_RE = re.compile(r'([\w\s]+)\:\:([\w\:\/\s]+)')
SECTION_RE = re.compile(r'[\w\s]+\:$')
CSV_RE = re.compile(r',')
NUMERIC_RE = re.compile(r'[\-\d\.(e\-)(e\+)]+')
DG_FILE_RE = re.compile(r'\d{4}\-\d{2}\-\d{2}_\d{2}\-\d{2}\-\d{2}[\s\w]*\.csv')

def read_dg_log(path):
    dt = None
    run_no = None
    status = None
    vacuum = None
    pressure = None
    spike = None
    failures = []
    droplet_generator_id = None
    test_run = False
    with open(path) as f:
        # just read in-order for now: this might change if DG log is modified
        for line in f:
            line = line.strip()
            # leave in as output weird (should be ::)
            if line.startswith('Run No.'):
                run_no = int(line[8:])
                continue
            keyval = KEYVAL_RE.match(line)
            if keyval:
                key, val = keyval.group(1), keyval.group(2)
                if key == "Start Time":
                    dt = datetime.strptime(val, '%Y/%m/%d %H:%M')
                elif key == "Status":
                    status = val
                elif key == "Unit Number" or key == "Unit number":
                    droplet_generator_id = int(val)
                continue # bust out
            csv = CSV_RE.search(line)
            if csv:
                vals = [val.strip() for val in line.split(',')]
                # patternize vals[0]->[3] null check & float?
                if vals[1] == 'Failed':
                    failures.append(vals[0])
                if vals[1] == 'ParamRepeatTestMode':
                    test_run = (vals[2] == '1')
                if len(vals) < 4:
                    continue
                elif vals[0] == 'Vacuum':
                    vacuum_str = NUMERIC_RE.search(vals[3])
                    if vacuum_str:
                        vacuum = float(vacuum_str.group(0))
                elif vals[0] == 'Manifold Pressure Check':
                    pressure_str = NUMERIC_RE.search(vals[3])
                    if pressure_str:
                        pressure = float(pressure_str.group(0))
                elif vals[0] == 'Manifold Pressure Derivative Check':
                    spike_str = NUMERIC_RE.search(vals[3])
                    if spike_str:
                        spike = float(spike_str.group(0))
                continue # end csv
            
            section = SECTION_RE.match(line)
            if section:
                if section.group(0) == "Time Series Data:":
                    break # stop reading
    
    # TODO: enclosing logic has to ensure that the dg id actually exists
    if not test_run:
        return DropletGeneratorRun(datetime=dt,
                                   run_number=run_no,
                                   droplet_generator_id=droplet_generator_id,
                                   failed=(status != 'OK'),
                                   vacuum_time=vacuum,
                                   vacuum_pressure=pressure,
                                   spike=spike,
                                   failure_reason=",".join(failures) if failures else None)
    else:
        return None


def get_dg_event_trace(path):
    with open(path) as f:
        # just read in-order for now: this might change if DG log is modified
        in_event_section = False
        in_event_lines = False
        events = []
        for line in f:
            line = line.strip()
            if not in_event_section:
                section = SECTION_RE.match(line)
                if section:
                    in_event_section = True
            elif not in_event_lines:
                # read one addl line
                in_event_lines = True
            else:
                # already in events
                event = line.split(',')
                events.append((int(event[0]), event[1], float(event[2]), float(event[3]), float(event[4])))
    
    return events



class DGLogSource(QLBFileSource):
    """
    Yield the list of DG log files.  Return a tuple (dirname, )
    """
    def __init__(self, root, top_folders):
        self.root = root
        self.top_folders = top_folders.split(',')
    
    def path_iter(self, min_file_name='', min_file_dict=None):
        if min_file_dict is None:
            min_file_dict = dict()
        root_dirs = [(folder, os.path.join(self.root, folder)) for folder in self.top_folders]
        root_dirs = [dir for dir in root_dirs if os.path.exists(dir[1])]
        
        folders = []
        for folder, dir in root_dirs:
            min_file = min_file_dict.get(folder, min_file_name)
            for root, dirnames, files in os.walk(dir):
                for file in files:
                    if DG_FILE_RE.match(file) and file > min_file:
                        yield (folder, file)


