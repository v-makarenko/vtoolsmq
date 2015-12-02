from qtools.tests import *

# todo accessible from test superclass
class DataRow(list):
    def __init__(self, row):
        self.__cols = []
        for col in row.findAll('td'):
            self.__cols.append(col.string)

    def __len__(self):
        return len(self.__cols)

    def __getitem__(self, idx):
        return self.__cols[idx]

    def __setitem__(self, idx, val):
        pass

    def __delitem__(self, idx):
        pass

class DataTable(list):
    def __init__(self, table):
        if table.name == 'table':
            tbody = table.find('tbody')
            if tbody:
                body = tbody
            else:
                body = table

        self.__rows = []
        for row in body.findAll('tr'):
            tds = row.findAll('td')
            if len(tds) > 0:
                self.__rows.append(DataRow(row))

    def __len__(self):
        return len(self.__rows)

    def __getitem__(self, idx):
        return self.__rows[idx]

    def __setitem__(self, idx, val):
        pass

    def __delitem__(self, idx):
        pass

class TestMetricsController(TestController):

    def test_per_plate_dds(self):
        response = self.app.get(url(controller='metrics', action='per_plate', id=17175))
        
        html = response.html
        redgreen = self.get_redgreen_table(html)

        # test presences
        assert 'Event Count Mean' in redgreen.text
        assert 'Event Count &lt; 12000' in redgreen.text
        assert 'Event Quality &lt; 0.85' in redgreen.text
        assert 'Singleplex Uniformity' in redgreen.text
        assert '2 per 8 wells' in redgreen.text
        assert 'Width' in redgreen.text
        assert 'Polydispersity' in redgreen.text

        dt = DataTable(redgreen)
        assert len(dt) == 7
        assert int(dt[0][2]) == 17387
        assert int(dt[0][3]) == 17430
        assert dt[1][2] == '0/48'
        assert dt[1][3] == '0/48'
        assert dt[2][2] == '0/48'
        assert dt[2][3] == '1/48'
        assert dt[3][2] == '3.9%'
        assert dt[3][3] == '4.4%'
        assert dt[4][2] == '0.45'
        assert dt[4][3] == '0.00'
        assert dt[5][2] == '8.77'
        assert dt[5][3] == '9.04'
        assert dt[6][2] == '0.03%'
        assert dt[6][3] == '0.06%'

        st = self.get_data_table(html, 2)
        assert st[0][1] == '758.0'
        assert st[0][2] == '742.0-771.9'
        assert st[1][1] == '1.07'
        assert st[4][1] == '34.73'

        et = self.get_data_table(html, 3)
        assert et[0][1] == '17387'

        ct1 = self.get_data_table(html, 4)
        assert ct1[0][4] == '2.3'

        ct2 = self.get_data_table(html, 5)
        assert ct2[0][1] == '446.2'

        wt = self.get_data_table(html, 6)
        assert wt[0][1] == '8.77'

        gt = self.get_data_table(html, 7)
        assert gt[3][1] == '0.9, 1.6'

    def test_per_reader(self):
        response = self.app.get(url(controller='metrics', action='certification', id='p10320'))
        assert 'Prod 10320' in response.text

        html = response.html

        redgreen = self.get_redgreen_table(html)

        # test presences
        assert 'Event Count Mean' in redgreen.text
        assert 'Event Count &lt; 12000' in redgreen.text
        assert 'Event Quality &lt; 0.85' in redgreen.text
        assert 'Singleplex Uniformity' in redgreen.text
        assert '2 per 8 wells' in redgreen.text
        assert 'Width' in redgreen.text
        assert 'Polydispersity' in redgreen.text
        assert 'FAM 350nM Amplitude' in redgreen.text
        assert 'FAM 350nM CV' in redgreen.text
        assert 'VIC 350nM Amplitude' in redgreen.text
        assert 'VIC 350nM CV' in redgreen.text
        #assert 'Identity Matrix' in redgreen.text

        dt = DataTable(redgreen)

        assert int(dt[0][2]) == 17387
        assert dt[1][2] == '0/48'
        assert dt[2][2] == '0/4'
        assert dt[3][2] == '0/48'
        assert dt[4][2] == '3.9%'
        assert dt[5][2] == '18653'
        assert dt[6][2] == '2.2%'
        assert dt[7][2] == '9772'
        assert dt[8][2] == '1.7%'
        #assert dt[9][2] == '0/1'
        assert dt[9][2] == '0.45'
        assert dt[10][2] == '8.76'
        assert dt[11][2] == '0.03%'

        bt = self.get_data_table(html, 1)
        assert bt[1][1] == '100'

        st = self.get_data_table(html, 2)
        assert st[0][1] == '758.0'
        assert st[0][2] == '742.0-771.9'
        assert st[1][1] == '1.07'
        assert st[4][1] == '34.73'

    def test_overview(self):
        response = self.app.get(url(controller='metrics', action='overview', id=48))
        assert "Rev C ENG Pilots Round 2" in response.text

        html = response.html
        bt = self.get_data_table(html, 0)
        assert bt[0][1] == '30'
        assert bt[1][1] == '1688'
        assert bt[2][1] == '211 (12.5%)'
        assert bt[3][1] == '21/1032 (2.0%)'
        assert bt[4][1] == '25/1032 (2.4%)'
        assert bt[7][1] == '0.46%'

        ct = self.get_data_table(html, 1)
        assert ct[0][2] == '13687'
        assert ct[1][2] == '36/240'
        assert ct[2][2] == '2/240'
        assert ct[3][2] == '11.9%'
        assert ct[4][2] == '8.79'
        assert ct[5][2] == '0.50%'
        assert ct[6][2] == '0.35%'
        assert ct[7][2] == '0.05%'

        ct2 = self.get_data_table(html, 2)
        assert ct2[0][2] == '0.2'

        st = self.get_data_table(html, 4)
        assert st[0][1] == '1117.1'
        assert st[1][1] == '13.1%'
        assert st[2][1] == '1.00'
        assert st[3][1] == '8690'

        dt = self.get_data_table(html, 5)
        assert dt[0][1] == '134.5'
        assert dt[1][1] == '264.0'
        assert dt[2][1] == '517.0'
        assert dt[3][1] == '1016.3'
        assert dt[4][1] == '2018.4'
        assert dt[5][1] == '1000.7'

        cnv = self.get_data_table(html, 10)
        assert cnv[0][1] == '1'
        assert cnv[0][3] == '1.01, 0.15'
        assert cnv[1][1] == '0'
        assert cnv[1][3] == '1.96, 0.09'
        assert cnv[2][1] == '0'
        assert cnv[2][3] == '2.93, 0.07'
        assert cnv[3][1] == '0'
        assert cnv[3][3] == '3.90, 0.13'
        assert cnv[4][1] == '0'
        assert cnv[4][3] == '4.75, 0.13'
        assert cnv[5][1] == '0'
        assert cnv[5][3] == '5.87, 0.12'

        rt = self.get_data_table(html, 11)
        assert rt[0][1] == '2.6'

        cct = self.get_data_table(html, 12)
        assert cct[0][1] == '20000'
        assert cct[1][1] == '2391'
        assert cct[2][1] == '9999'
        assert cct[3][1] == '1989'

        wt = self.get_data_table(html, 13)
        assert wt[0][1] == '8.83'
        assert wt[1][1] == '0.81'
        assert wt[2][1] == '17.0%'
        assert wt[3][1] == '0.46%'
        assert wt[4][1] == '0.52%'

        gt = self.get_data_table(html, 15)
        assert gt[3][1] == '8.0, 4.0'

        blt = self.get_data_table(html, 16)
        assert blt[0][1] == '203.54'


    def get_redgreen_table(self, htmltree):
        datagrids = htmltree.findAll('table', 'datagrid')
        return datagrids[0]

    def get_data_table(self, htmltree, index):
        return DataTable(htmltree.findAll('table', 'datagrid')[index])

