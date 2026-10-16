# SPDX-License-Identifier: GPL-2.0-or-later
import unittest
from usgs_catalogo_qgis.tools.validate_accuracy import evaluate,LABELS

class AccuracyValidationTests(unittest.TestCase):
 def rows(self,n=60):return [{'uuid':str(i),'reference':LABELS[i%3],'prediction':LABELS[i%3]} for i in range(n)]
 def test_inconclusive_does_not_inflate_accuracy(self):
  rows=self.rows()
  for r in rows[:30]:r['prediction']='inconclusivo'
  value=evaluate(rows);self.assertEqual(value['accuracy_all_cases'],.5);self.assertEqual(value['accuracy_answered'],1)
  self.assertFalse(value['target_demonstrated_in_this_sample'])
 def test_small_perfect_sample_is_not_validation(self):
  value=evaluate(self.rows(9));self.assertFalse(value['target_demonstrated_in_this_sample'])
 def test_supported_perfect_sample_is_only_sample_specific(self):
  value=evaluate(self.rows());self.assertTrue(value['target_demonstrated_in_this_sample']);self.assertIn('Não demonstra generalização',value['scope'])
 def test_majority_class_cannot_hide_errors(self):
  rows=[{'uuid':str(i),'reference':'manter' if i<90 else ('contestar' if i<95 else 'revisar_data'),'prediction':'manter'} for i in range(100)]
  value=evaluate(rows);self.assertEqual(value['accuracy_all_cases'],.9);self.assertAlmostEqual(value['balanced_accuracy'],1/3)
  self.assertFalse(value['target_demonstrated_in_this_sample'])
 def test_duplicates_invalid_labels_and_empty_rejected(self):
  for rows in [[],[{'uuid':'a','reference':'unknown','prediction':'manter'}],self.rows(1)*2]:
   with self.assertRaises(ValueError):evaluate(rows)
