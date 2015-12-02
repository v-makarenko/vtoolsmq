# TODO: put in PyQLB instead?
def width_gate_sigma(well):
    # show how wide the stdevs for gating were,
    # based off of plate version.  This may need
    # to be revised with v1.5 QLP, which can have
    # variable width sigmas per well, in theory.
    #
    # TODO: check major/minor of well
     
    major, minor = well.plate.quantitation_algorithm_tuple
    if major >= 0 and minor >= 24:
        return 3.5
    elif major == 0 and minor >= 20:
        return 2.5
    else:
        return 2