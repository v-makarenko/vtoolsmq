import json

from qtools.model import Session

from qtools.model.reagents import ValidationTestTemplate
from qtools.model.reagents.templates import *

from . import QToolsCommand

from qtools.lib.webservice.neb import read_neb_enzyme_price_list, read_neb_buffer_list, NEBEnzymeSource
from qtools.lib.webservice.ucsc import get_rebase_records


class SetupReagentsCommand(QToolsCommand):
    summary = "Sets up the target database with starter reagent validation models."
    usage = "paster --plugin=qtools setup-reagents [config]"

    def command(self):
        self.load_wsgi_app()

        self._setup_test_templates()

    def _setup_test_templates(self):
        templates = [ValidationTestTemplate(name='Control A-Test-Control B',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_16P_CTC)),
                     ValidationTestTemplate(name='Control A-Test A-Control B-Test B',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_16P_CTCT)),
                     ValidationTestTemplate(name='1 Control, 1 Test, Odd Cols',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_8P_ODD)),
                     ValidationTestTemplate(name='1 Control, 1 Test, Even Cols',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_8P_EVEN)),
                     ValidationTestTemplate(name='1 Control, 1 Test, Left Half',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_16P_CT_LEFT)),
                     ValidationTestTemplate(name='1 Control, 1 Test, Right Half',
                                            layout_json=json.dumps(VALIDATION_LAYOUT_8N_16P_CT_RIGHT))]
        for temp in templates:
            temp_obj = Session.query(ValidationTestTemplate).filter_by(name=temp.name).first()
            if not temp_obj:
                Session.add(temp)

        # TODO: commit at end of command instead?
        Session.commit()
