
import os
import re
import sys
from os.path import dirname

ta_name = "stigs_in_splunk"
pattern = re.compile(r"[\\/]etc[\\/]apps[\\/][^\\/]+[\\/]bin[\\/]?$")
new_paths = [path for path in sys.path if not pattern.search(path) or ta_name in path]
new_paths.insert(0, os.path.join(dirname(dirname(__file__)), "lib"))
new_paths.insert(0, os.path.sep.join([os.path.dirname(__file__), ta_name]))
sys.path = new_paths

# splunktaucclib 7.x raises 404 when UCC Configuration lists all entities (name=None).
try:
    from splunktaucclib.rest_handler.endpoint import MultipleModel

    _orig_model = MultipleModel.model

    def _model(self, name):
        if name is None:
            fields = []
            for item in self.models.values():
                fields.extend(item.fields)

            class _Union:
                pass

            union = _Union()
            union.fields = fields
            return union
        return _orig_model(self, name)

    MultipleModel.model = _model
except Exception:
    pass
