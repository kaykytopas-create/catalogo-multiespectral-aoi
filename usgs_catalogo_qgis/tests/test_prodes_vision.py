import json
import tempfile
import unittest
from pathlib import Path
from usgs_catalogo_qgis.prodes_vision import LocalVision,validate_answer,NoRedirect
from usgs_catalogo_qgis.prodes import ProdesError

class VisionTests(unittest.TestCase):
    def answer(self):return {'observations':[{'scene_ids':['a'],'pattern':'indeterminado','description':'Apenas hipótese visual.'}],
                            'argument':'Conferir a imagem oficial.','references':['INPE_REVIEW'],'limitations':'Sem validação temática.'}
    def test_unknown_scene_and_reference_are_rejected(self):
        answer=self.answer();validate_answer(answer,{'a'},{'INPE_REVIEW'})
        answer['observations'][0]['scene_ids']=['inventada']
        with self.assertRaises(ProdesError):validate_answer(answer,{'a'},{'INPE_REVIEW'})
        answer=self.answer();answer['references']=['lei_inventada']
        with self.assertRaises(ProdesError):validate_answer(answer,{'a'},{'INPE_REVIEW'})
    def test_cannot_return_replacement_verdict(self):
        answer=self.answer();answer['verdict']='Falso PRODES'
        with self.assertRaises(ProdesError):validate_answer(answer,{'a'},{'INPE_REVIEW'})
    def test_local_inference_passes_images_and_keeps_receipts(self):
        class Fixture(LocalVision):
            def request(self,path,data=None):
                if path=='/api/show':return {'capabilities':['vision']}
                self.calls=data
                return {'message':{'content':json.dumps(VisionTests().answer())}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'a.png';path.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            client=Fixture()
            result=client.analyse('fixture:local',{'agent':{'references':[{'id':'INPE_REVIEW'}]}},[{'filename':str(path),'scene_id':'a'}])
            self.assertTrue(client.calls['messages'][1]['images'])
            self.assertIn('sha256',result['image_receipts'][0]);self.assertNotIn('verdict',result)
    def test_text_only_model_and_redirects_rejected(self):
        class Text(LocalVision):
            def request(self,*args):return {'capabilities':['completion']}
        with self.assertRaises(ProdesError):Text().inspect('local')
        with self.assertRaises(ProdesError):NoRedirect().redirect_request(None,None,None,None,None,None)
        with self.assertRaises(ProdesError):LocalVision().request('/api/pull',{})

    def test_remote_models_rejected_before_uploading_images(self):
        class Remote(LocalVision):
            def request(self,*args):return {'capabilities':['vision'],'remote_host':'https://example.org','remote_model':'vision'}
        with self.assertRaises(ProdesError):Remote().inspect('vision:local')
        with self.assertRaises(ProdesError):Remote().inspect('vision:cloud')
