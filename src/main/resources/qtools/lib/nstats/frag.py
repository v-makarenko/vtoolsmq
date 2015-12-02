"""
Created on Wed Feb 09 15:11:17 2011

@author: SDube
"""

# Compute Probability of Fragmentation
# See Main routine for usage

import numpy as np

# TODO move this stuff to common (conf_interval already exists)
def binomial_fit(x, n):
    # Binomial Proportion Interval
    p = (x+2)/(n+4)
    s = np.sqrt(p*(1-p)/n)
    p_low = p - 1.96 * s;
    p_high = p + 1.96 * s;
    p_low = max(p_low, 0)
    p_high = min(p_high, 1)
    return p, p_low, p_high

def conc_conf_interval(x, n):
    p, p1, p2 = binomial_fit(x, n)
    c = -np.log(1 - p)
    c_low = -np.log(1 - p1)
    c_high = -np.log(1 - p2)
    return c, c_low, c_high

def cnv_conf_interval(y, x, ny, nx):
    #x is numerator and y is denominator
    cx, cxl, cxh = conc_conf_interval(x, nx)
    cy, cyl, cyh = conc_conf_interval(y, ny)
    h_T = cxh - cx
    h_B = cx - cxl
    w_R = cyh - cy
    w_L = cy - cyl
    t1 = cx * cy;
    t2 = (h_B**2 - cx**2)*(w_R**2 - cy**2)
    t3 = cy**2 - w_R**2
    r = cx/cy
    if t1*t1 >= t2:
        r_low = (t1 - np.sqrt(t1*t1 - t2))/t3;
    else:
        r_low = np.nan
    t2 = (h_T**2 - cx**2)*(w_L**2 - cy**2)
    t3 = cy**2 - w_L**2
    if t1*t1 >= t2:
        r_high = (t1 + np.sqrt(t1*t1 - t2))/t3;
    else:
        r_high = np.nan
    return r, r_low, r_high
    
    
def prob_of_frag(fampos_vicneg, fampos_vicpos,
                 famneg_vicneg, famneg_vicpos,
                 total_events):
    # if rank of matrix < 2
    if((fampos_vicneg == 0 and fampos_vicpos == 0) \
       or (fampos_vicneg == 0 and famneg_vicneg == 0) \
       or (fampos_vicpos == 0 and famneg_vicpos == 0) \
       or (famneg_vicneg == 0 and famneg_vicpos == 0)):
       return None
        
    H = np.array([[fampos_vicneg*1., fampos_vicpos*1.],
                  [famneg_vicneg*1., famneg_vicpos*1.]])
     
    # Compute Probabilities
    estN = np.sum(H.flatten())
    i_p = H/estN
    
    # A is X and B is Y in cross plot
    i_pAorAB = i_p[0,1] + i_p[1,1]
    i_pBorAB = i_p[0,0] + i_p[0,1]
    i_cAorAB = -np.log(1 - i_pAorAB)
    i_cBorAB = -np.log(1 - i_pBorAB)
    
    maxVal = min(i_cAorAB, i_cBorAB)
    delta = maxVal/1000.0;
    
    errArr = []
    gcABArr = []
    
    gp = np.zeros((2, 2))
    
    for gcAB in np.arange(0, maxVal, delta):
        gcA = i_cAorAB - gcAB
        gcB = i_cBorAB - gcAB
        
        gpA = 1 - np.exp(-gcA)
        gpB = 1 - np.exp(-gcB)
        gpAB = 1 - np.exp(-gcAB)
        
        gp[1,0] = (1 - gpA) * (1 - gpB) * (1 - gpAB)
        gp[1,1] = gpA * (1 - gpB) * (1 - gpAB)
        gp[0,0] = (1 - gpA) * gpB * (1 - gpAB)
        gp[0,1] = 1 - gp[1,0] - gp[1,1] - gp[0,0]
        
        gH = gp * estN
        
        err = np.sqrt(np.sum((H.flatten() - gH.flatten())**2))
        
        errArr.append(err)
        gcABArr.append(gcAB)
    
    minidx = np.argmin(errArr)
    estAB = gcABArr[minidx]
    estA = i_cAorAB - estAB
    estB = i_cBorAB - estAB
    
    cntA, cntB, cntAB = round(estA*estN), round(estB*estN), round(estAB*estN)
    
    gpA = 1 - np.exp(-estA)
    gpB = 1 - np.exp(-estB)
    gpAB = 1 - np.exp(-estAB)
    
    cA, c_lowA, c_highA = conc_conf_interval(gpA * estN, estN)
    cB, c_lowB, c_highB = conc_conf_interval(gpB * estN, estN)
    cAB, c_lowAB, c_highAB = conc_conf_interval(gpAB * estN, estN)
    
    gpAhalf = 1 - np.exp(-estA * .5)
    gpBhalf = 1 - np.exp(-estB * .5)
    px = gpAhalf + gpBhalf - gpAhalf * gpBhalf
    py = gpAB + gpAhalf + gpBhalf - gpAB * gpAhalf - gpAB * gpBhalf - gpAhalf * gpBhalf + gpAB * gpAhalf * gpBhalf
    r, rlow, rhigh = cnv_conf_interval(py*estN, px*estN, estN, estN)
    
    retarr = [[r, max(0.0, rlow), min(1.0, rhigh)], [cntA, round(c_lowA*estN), round(c_highA*estN)],\
              [cntB,round(c_lowB*estN),round(c_highB*estN)],[cntAB,round(c_lowAB*estN),round(c_highAB*estN)]]
    
    # show concentrations
    # may need to add droplet volume to this calc
    if ( total_events is not None and total_events > 0 ):
        nL_ratio = 1000.0/total_events
    else:
        nL_ratio = 0

    for i in range(1,4):
        retarr[i].extend([nL_ratio*val for val in retarr[i]])
    
    return retarr
