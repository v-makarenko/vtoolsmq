from qtools.lib.nstats import interval_averages, moving_average_by_interval
import unittest

class TestFunctions(unittest.TestCase):

    def test_interval_averages(self):
        interval_width = 100
        array = [1, 4, 5, 2, 2, 6]
        interval_array = [90, 100, 150, 200, 300, 500]

        avgs = interval_averages(array, interval_array, interval_width)
        intervals, vals = zip(*avgs)
        assert intervals == (0.0,100.0,200.0,300.0,400.0,500.0)
        assert vals == (1.0, 4.5, 2.0, 2.0, 2.0, 6.0)

        array = [1, 4, 5, 2, 3, 6]
        interval_array = [-10, 40, 75, 225, 250, 475]
        avgs = interval_averages(array, interval_array, 50)
        intervals, vals = zip(*avgs)
        assert intervals == (-50.0, 0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0)
        assert vals == (1.0, 4.0, 5.0, 5.0, 5.0, 2.0, 3.0, 3.0, 3.0, 3.0, 6.0, 6.0)

        avgs = interval_averages(array, interval_array, 50, fill_blanks=False)
        intervals, vals = zip(*avgs)
        assert intervals == (-50.0, 0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0)
        assert vals == (1.0, 4.0, 5.0, None, None, 2.0, 3.0, None, None, None, 6.0, None)

        avgs = interval_averages(array, interval_array, 50, fill_blanks=False, blank_val=0.0)
        intervals, vals = zip(*avgs)
        assert intervals == (-50.0, 0.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0)
        assert vals == (1.0, 4.0, 5.0, 0.0, 0.0, 2.0, 3.0, 0.0, 0.0, 0.0, 6.0, 0.0)

    def test_moving_average_by_interval(self):
        interval_width = 100
        array = [1, 4, 5, 2, 2, 6]
        interval_array = [90, 100, 150, 200, 300, 500]
        avgs = moving_average_by_interval(array, interval_array, interval_width, 2)

        bins, vals = zip(*avgs)
        assert bins == (0.0, 100.0, 200.0, 300.0, 400.0, 500.0)
        assert vals == (1.0, 2.75, 3.25, 2.0, 2.0, 4.0)