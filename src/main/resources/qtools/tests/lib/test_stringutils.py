from qtools.lib.stringutils import *

def test_initial():
    assert initial("Serge Saxonov") == "SS"
    assert initial("Prince") == "P"
    assert initial("meek phrase") == "MP"

def test_militarize():
    assert militarize("Serge Saxonov") == "SerSax"
    assert militarize("Paul Lu") == "PauLu"
    assert militarize("Serge Saxonov", 4) == "SergSaxo"
    assert militarize("lower case text") == "LowCasTex"
    assert militarize("PhD") == "Phd" # wonky case, not gonna handle it now
    assert militarize("PWD") == "PWD"

def test_camelize():
    assert camelize("Serge Saxonov") == "SergeSaxonov"
    assert camelize("Serge Saxonov's Desk") == "SergeSaxonovsDesk"
    assert camelize("DNA Lovers' Forum") == "DNALoversForum"