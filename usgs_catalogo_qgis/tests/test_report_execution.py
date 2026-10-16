import importlib.util
import pathlib
import struct
import tempfile
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / 'prodes_report.py'
spec = importlib.util.spec_from_file_location('usgs_catalogo_qgis.prodes_report', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExecutionReportTests(unittest.TestCase):
    def test_manual_report_does_not_claim_historical_search(self):
        row = {'year':2020, 'uuid':'a', 'contestability':{'status':'Passível de contestação'}}
        result = module.readable_report({}, [row])
        self.assertIn('Histórico anterior/posterior não pesquisado', result)
        self.assertIn('não houve busca automática', result)
        self.assertNotIn('A busca automática consultou', result)

    def test_landscape_map_has_explicit_proportional_height(self):
        with tempfile.NamedTemporaryFile(suffix='.png') as image:
            image.write(b'\x89PNG\r\n\x1a\n' + b'\0'*8 + struct.pack('>II', 2104, 1487))
            image.flush()
            tag = module.image_tag(image.name)
            self.assertIn('width="640" height="452"', tag)

    def test_primary_button_routes_to_history_not_manual_selectors(self):
        source = path.with_name('prodes_ui.py').read_text()
        start = source.index('    def analyse_automatic(self):')
        end = source.index('    def analyse_selected_images(self):', start)
        method = source[start:end]
        self.assertIn('self.analyse_autofetch()', method)
        self.assertNotIn('automatic_payload()', method)
