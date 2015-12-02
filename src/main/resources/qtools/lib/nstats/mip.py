# -*- coding: utf-8 -*-
"""
Created on Thu May 12 11:00:45 2011

@author: SDube
"""
from pyqlb.nstats.meta_analysis import *
from pyqlb.nstats.peaks import cluster_1d
from qtools.lib.nstats.peaks import accepted_peaks
import numpy as np

def count_positives_in_well(well, channel):
    # return count of positives and total events
    from pyqlb.nstats.peaks import cluster_1d, width_gated, quality_gated
    chn_stats = well.channels[channel].statistics
    threshold = chn_stats.threshold
    min_width_gate = chn_stats.min_width_gate
    max_width_gate = chn_stats.max_width_gate
    min_quality_gate = chn_stats.min_quality_gate
    accepted_events = accepted_peaks(well)
    positives, negatives = cluster_1d(accepted_events, channel, threshold)
    return len(positives), len(positives)+len(negatives)
    
def process_replicate(replicate_wells, fam_fpr, vic_fpr, ref_channel):
    well_keys = replicate_wells.keys()
    fam_pos_arr = zeros(len(well_keys))
    fam_tot_arr = zeros(len(well_keys))
        
    #process first channel of replicate wells
    # TODO for Simant: show items() iter
    for j in range(len(well_keys)):
        well = replicate_wells[well_keys[j]]
        num_pos, num_total = count_positives_in_well(well, 0)
        fam_pos_arr[j] = num_pos
        fam_tot_arr[j] = num_total
        
    m_total, s_total_in_percent, s_poisson_in_percent, s_realworld_in_percent, total_s_arr, p_val=process_conc_replicates(fam_pos_arr, fam_tot_arr, fam_fpr)
    fam_conc = m_total
    fam_total_sd = s_total_in_percent/100.0
    fam_poisson_sd = s_poisson_in_percent/100.0
       
    #process second channel of replicate wells
    if len(well.channels) == 2:
        vic_pos_arr = zeros(len(well_keys))
        vic_tot_arr = zeros(len(well_keys))
            
        for j in range(len(well_keys)):
            well = replicate_wells[well_keys[j]]
            num_pos, num_total = count_positives_in_well(well, 1)
            vic_pos_arr[j] = num_pos
            vic_tot_arr[j] = num_total 
            
        m_total, s_total_in_percent, s_poisson_in_percent, s_realworld_in_percent, total_s_arr, p_val=process_conc_replicates(vic_pos_arr, vic_tot_arr, vic_fpr)
        vic_conc = m_total
        vic_total_sd = s_total_in_percent/100.0
        vic_poisson_sd = s_poisson_in_percent/100.0
         
        if ref_channel == 0:
            m_total, s_total_in_percent, s_poisson_in_percent, s_realworld_in_percent, total_s_arr, p_val=process_cnv_replicates(vic_pos_arr, vic_tot_arr, fam_pos_arr, fam_tot_arr, vic_fpr, fam_fpr)
        else:
            m_total, s_total_in_percent, s_poisson_in_percent, s_realworld_in_percent, total_s_arr, p_val=process_cnv_replicates(fam_pos_arr, fam_tot_arr, vic_pos_arr, vic_tot_arr, fam_fpr, vic_fpr)
            
        cnv = m_total
        cnv_total_sd = s_total_in_percent/100.0
        cnv_poisson_sd = s_poisson_in_percent/100.0
           
        ret_vals = [fam_conc, fam_total_sd, fam_poisson_sd, vic_conc, vic_total_sd, vic_poisson_sd, cnv, cnv_total_sd, cnv_poisson_sd]
    else:
        ret_vals = [fam_conc, fam_total_sd, fam_poisson_sd, None, None, None, None, None, None]
            
    return ret_vals