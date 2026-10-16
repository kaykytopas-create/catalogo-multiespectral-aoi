# SPDX-License-Identifier: GPL-2.0-or-later
"""Evaluate independently reviewed UUIDs; does not manufacture an accuracy claim.
CSV fields: uuid,reference,prediction. Labels: revisar_data,contestar,manter;
prediction also accepts inconclusivo. No training or network operations.
"""
import argparse,csv,json,math
LABELS=('revisar_data','contestar','manter')


def evaluate(records, target=.8, minimum=50):
    seen=set();matrix={label:{p:0 for p in (*LABELS,'inconclusivo')} for label in LABELS}
    for row in records:
        ident=str(row.get('uuid','')).strip();truth=row.get('reference');prediction=row.get('prediction')
        if not ident or ident in seen:raise ValueError('UUID vazio ou duplicado: avalie unidades distintas.')
        if truth not in LABELS or prediction not in (*LABELS,'inconclusivo'):raise ValueError('Classe não reconhecida no CSV.')
        seen.add(ident);matrix[truth][prediction]+=1
    n=len(seen)
    if not n:raise ValueError('Sem casos revisados.')
    correct=sum(matrix[label][label] for label in LABELS)
    abstained=sum(matrix[label]['inconclusivo'] for label in LABELS);answered=n-abstained
    support={label:sum(matrix[label].values()) for label in LABELS}
    recall={label:matrix[label][label]/support[label] if support[label] else None for label in LABELS}
    precision={label:matrix[label][label]/sum(matrix[truth][label] for truth in LABELS) if sum(matrix[truth][label] for truth in LABELS) else None for label in LABELS}
    accuracy=correct/n;p=accuracy;z=1.96
    lower=(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
    balanced=sum(v for v in recall.values() if v is not None)/sum(v is not None for v in recall.values())
    supported=n>=minimum and all(support[label]>=10 for label in LABELS)
    return {'cases':n,'correct':correct,'errors':n-correct-abstained,'inconclusive':abstained,
            'accuracy_all_cases':accuracy,'coverage':answered/n,'accuracy_answered':correct/answered if answered else None,
            'balanced_accuracy':balanced,'recall':recall,'precision':precision,'support':support,'confusion_matrix':matrix,
            'wilson_lower_95':max(0,lower),'target':target,'adequate_support':supported,
            'target_demonstrated_in_this_sample':supported and lower>=target and balanced>=target,
            'scope':'Somente estes casos. Inconclusivos não contam como acerto. Não demonstra generalização, independência dos casos ou acurácia em novos imóveis.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('csv');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    with open(args.csv,encoding='utf-8-sig',newline='') as stream:result=evaluate(csv.DictReader(stream))
    with open(args.output,'w',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print('Casos: {}; acurácia global: {:.1%}; inconclusivos: {}; meta demonstrada nesta amostra: {}'.format(result['cases'],result['accuracy_all_cases'],result['inconclusive'],result['target_demonstrated_in_this_sample']))

if __name__=='__main__':main()
