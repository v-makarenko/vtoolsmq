from qtools.setests import SeleniumContextTest, CSS
import re, time


class PlateViewTest(SeleniumContextTest):

    @SeleniumContextTest.requires_db_property_startswith(host='localhost')
    def test_metrics(self):
        a11_well_values = {'sample_name'              : u'48H',
                           'accepted_event_count'     : u'14723',
                           'accepted_width_cv'        : u'2.9%',
                           'accepted_width_mean'      : u'8.43',
                           'accepted_width_stdev'     : u'0.25',
                           'balance_score'            : u'1.64',
                           'min_amplitude_ratio'      : u'0.0%',
                           'carryover_peaks'          : u'--',
                           'cluster_mode'             : u'Cluster',
                           'cluster_conf'             : u'1.00',
                           'cnv'                      : u'2.076',
                           'vic_fam_cnv_ratio'        : u'1.927',
                           'cnv_rise_ratio'           : u'1.07',
                           'fragmentation_probability': u'100.0%',
                           'gated_out_event_pct'      : u'6.0%',
                           'short_interval_count_ratio':u'28.2%',
                           'rejected_peak_ratio'      : u'2.4%',
                           'total_event_count'        : u'15655',
                           'vertical_streak_ratio'    : u'5.1%',
                           'width_mean'               : u'8.45',
                           'width_variance'           : u'0.56',
                           'width_cv'                 : u'6.7%'}

        a11_channel_values = {
            'target'                    : ('XNA','RPP30_6'),
            'type'                      : ('Unknown','Unknown'),
            'amplitude_cv_pct'          : ('65.4%','59.1%'),
            'amplitude_mean'            : ('6751','4807'),
            'amplitude_stdev'           : ('4417.1','2840.2'),
            'baseline_mean'             : ('245.3','263.0'),
            'baseline_stdev'            : ('24.58','18.21'),
            'concentration'             : ('1049.0','1010.5'),
            'concentration_rise_ratio'  : ('1.07','1.00'),
            'clusters_automatic'        : ('Automatic','Automatic'),
            'extracluster'              : ('0.7%','0.9%'),
            'revb_extracluster'         : ('1.2%','1.3%'),
            'gap_rain_droplets'         : ('--','--'),
            'negative_peaks'            : ('5668','5870'),
            'nonpositive_amplitude_cv_pct': ('8.8%','9.4%'),
            'nonpositive_mean'          : ('1181','1343'),
            'nonpositive_stdev'         : ('104.3','126.8'),
            'nonpositive_kurtosis'      : ('0.15','0.23'),
            'nonpositive_snr'           : ('11.32','10.60'),
            'nonpositive_skew'          : ('0.32','-0.02'),
            'ntc_positives'             : ('--','--'),
            'polydispersity'            : ('0.12%','0.11%'),
            'revb_polydispersity'       : ('0.12%','0.11%'),
            'positive_peaks'            : ('9055','8853'),
            'positive_amplitude_cv_pct' : ('3.7%','5.9%'),
            'positive_mean'             : ('10237','7104'),
            'positive_stdev'            : ('377.9','418.4'),
            'positive_kurtosis'         : ('0.95','0.03'),
            'positive_snr'              : ('27.09','16.98'),
            'positive_skew'             : ('-0.29','-0.58'),
            'rain_p_plus_pct'           : ('0.00%','0.00%'),
            'rain_p_pct'                : ('0.25%','0.41%'),
            'rain_p_minus_pct'          : ('0.01%','0.02%'),
            's_value'                   : ('18.64','10.49'),
            'threshold'                 : ('3032','2683'),
            'threshold_conf'            : ('0.97','0.99')
        }
        self.driver.get(self.url(controller='plate', action='view', id=21749))
        overlay_select = CSS(self.driver, '#display_selector')[0]
        a11 = CSS(self.driver, 'div[rel=A11]')[0]
        a11_well_overlay = CSS(a11, '.well_stat')[0]
        a11_fam_overlay = CSS(a11, '.stat0')[0]
        a11_vic_overlay = CSS(a11, '.stat1')[0]

        for attr, desired_value in a11_well_values.items():
            option = CSS(overlay_select, "option[value=%s]" % attr)[0]
            option.click()
            #just give a little time
            time.sleep(0.1)
            assert not a11_fam_overlay.is_displayed()
            assert not a11_vic_overlay.is_displayed()
            assert a11_well_overlay.is_displayed()
            assert a11_well_overlay.text == desired_value

        for attr, (desired_fam_value, desired_vic_value) in a11_channel_values.items():
            option = CSS(overlay_select, "option[value=%s]" % attr)[0]
            option.click()

            time.sleep(0.1)
            assert not a11_well_overlay.is_displayed()
            assert a11_fam_overlay.is_displayed()
            assert a11_vic_overlay.is_displayed()

            assert a11_fam_overlay.text == desired_fam_value
            assert a11_vic_overlay.text == desired_vic_value
