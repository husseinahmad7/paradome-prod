"""Freeze development/calibration policy before touching the fresh v2 test.

--verify uses checked-in numeric evidence and frozen calibration, never refits.
The v1 report and its tested policy remain archived unchanged.
"""
import argparse
import hashlib
import json
import statistics
from time import perf_counter
from evaluate import read, rank_metrics, fit, confidence, operating_point, reliability, aggregate
from engineering import search
from engineering.related_search import expand_related, unrelated_margin

ROOT=search.ROOT
ARTIFACT=search.ARTIFACT_ROOT
def write(path,value):
    path.write_bytes((json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())
def digest(path):
    data=path.read_bytes()
    if path.suffix=='.py': data=data.replace(b'\r\n',b'\n')
    return hashlib.sha256(data).hexdigest()
def summarize(rows,calibrator):
    return {split:{'queries':len(part),'semantic':aggregate(part,'semantic'),'cosine':aggregate(part,'cosine'),'bm25':aggregate(part,'bm25'),'operating_point':operating_point(part,calibrator,calibrator['threshold']),**reliability(part,calibrator)} for split in ('development','calibration','test') if (part:=[r for r in rows if r['query']['split']==split])}

def main(verify=False):
    frozen=read(ROOT/'frozen-v2.json')
    for name,expected in frozen['sha256'].items():
        if digest(ROOT/'data'/name)!=expected: raise RuntimeError('v2 corpus/labels changed; create a fresh experiment.')
    report_path=ROOT/'evaluation-v2.json'
    if not verify and report_path.exists(): raise RuntimeError('v2 test has been inspected. A revision requires another fresh holdout.')
    docs=search.corpus('v2')[0]['documents']; corpus_hash=search.corpus('v2')[1]
    queries=read(ROOT/'data/queries-v2.json')['queries']
    vector_path=ARTIFACT/'evaluation-vectors-v2.json'
    if verify:
        evidence=read(vector_path)
        vectors=read(ARTIFACT/'search-index-v2.json')['vectors']
        encoded_queries=evidence['queries']
    else:
        encoded=read(ROOT/'encoded-v2.json')
        assert [d['id'] for d in docs]==[d['id'] for d in encoded['documents']]
        vectors=[search.normalize_vector(d['vector']) for d in encoded['documents']]
        encoded_queries=encoded['queries']
    query_vectors={q['id']:search.normalize_vector(q['vector']) for q in encoded_queries}
    def evaluate(query):
        start=perf_counter(); vector=query_vectors[query['id']]
        raw=sorted([(doc,max(-1.,min(1.,sum(a*b for a,b in zip(vector,v))))) for doc,v in zip(docs,vectors)],key=lambda pair:(-pair[1],pair[0]['id']))
        ranked=expand_related(raw); semantic_ms=(perf_counter()-start)*1000
        ids=[d['id'] for d,_ in ranked]; cosine=[d['id'] for d,_ in raw[:5]]
        start=perf_counter(); bm25=[d['id'] for d,_ in search.keyword_rank(query['text'],version='v2')]; keyword_ms=(perf_counter()-start)*1000
        return {'query':query,'features':[raw[0][1],unrelated_margin(raw)],'top_relevant':int(ids[0] in query['relevance']),'semantic_ids':ids,'cosine_ids':cosine,'bm25_ids':bm25,'semantic':rank_metrics(ids,query['relevance']),'cosine':rank_metrics(cosine,query['relevance']),'bm25':rank_metrics(bm25,query['relevance']),'semantic_ms':semantic_ms,'keyword_ms':keyword_ms}
    # No test ranking before calibration/policy artifacts are frozen.
    rows=[evaluate(q) for q in queries if q['split']!='test']
    policy_path=ROOT/'policy-v2.json'; index_path=ARTIFACT/'search-index-v2.json'; calibration_path=ARTIFACT/'search-calibration-v2.json'
    contract=search.embedding_contract('v2')
    if verify:
        policy=read(policy_path); calibrator=read(calibration_path)
        assert policy['retriever_sha256']==digest(ARTIFACT.parent/'related_search.py')
        assert policy['index_sha256']==digest(index_path)
        assert policy['calibration_sha256']==digest(calibration_path)
        assert policy['query_vectors_sha256']==digest(vector_path)
    else:
        development=[r for r in rows if r['query']['split']=='development']; calibration=[r for r in rows if r['query']['split']=='calibration']
        calibrator=fit(development)
        candidates=[(t/1000,operating_point(calibration,calibrator,t/1000)) for t in range(1,1001)]
        qualified=[(t,p) for t,p in candidates if p['precision'] is not None and p['precision']>=.90 and p['coverage']>=.50]
        threshold,point=max(qualified,key=lambda pair:(pair[1]['f1'],pair[1]['coverage'],pair[0])) if qualified else (1.,operating_point(calibration,calibrator,1.))
        write(index_path,{'contract':contract,'corpus_sha256':corpus_hash,'document_ids':[d['id'] for d in docs],'vectors':vectors,'retrieval_policy':'cosine-related-v2'})
        calibrator.update(contract=contract,corpus_sha256=corpus_hash,index_sha256=digest(index_path),threshold=threshold,fit_split='development',threshold_split='calibration',features=['top cosine','margin to next unrelated discussion'],calibration_qualified=bool(qualified))
        write(calibration_path,calibrator)
        write(vector_path,{'contract':contract,'corpus_sha256':corpus_hash,'query_sha256':frozen['sha256']['queries-v2.json'],'runtime':encoded['runtime'],'queries':encoded_queries})
        policy={'retriever_sha256':digest(ARTIFACT.parent/'related_search.py'),'index_sha256':digest(index_path),'calibration_sha256':digest(calibration_path),'query_vectors_sha256':digest(vector_path),'holdout_sha256':frozen['sha256'],'test_inspected':False,'policy':frozen['policy']}
        write(policy_path,policy)
        write(ARTIFACT/'search-golden-v2.json',{'contract':contract,'assets':read(ROOT/'assets-lock-v1.json'),'goldens':encoded['goldens'],'tolerance':{'maximum_absolute_difference':.01,'minimum_cosine':.999}})
    rows.extend(evaluate(q) for q in queries if q['split']=='test')
    summary=summarize(rows,calibrator); test=[r for r in rows if r['query']['split']=='test']
    slices={kind:{mode:aggregate([r for r in test if r['query']['slice']==kind],mode) for mode in ('semantic','cosine','bm25')} for kind in ('literal','paraphrase','distractor')}
    passed=summary['test']['semantic']['recall_at_5']>=.85 and slices['paraphrase']['semantic']['recall_at_5']>slices['paraphrase']['bm25']['recall_at_5'] and calibrator['calibration_qualified']
    if verify:
        previous=read(report_path)
        # Probabilities rounded only for cross-platform numerical reproducibility.
        def rounded(value):
            if isinstance(value,float): return round(value,12)
            if isinstance(value,dict): return {key:rounded(v) for key,v in value.items()}
            if isinstance(value,list): return [rounded(v) for v in value]
            return value
        if rounded(summary)!=rounded(previous['splits']) or rounded(slices)!=rounded(previous['test_slices']) or passed!=previous['gate']['passed']: raise RuntimeError('v2 frozen evaluation does not reproduce')
        print('v2 frozen ranking, confidence, split digests and gate reproduce; no refit.',flush=True); return
    failures=[r for r in test if (r['semantic'] and r['semantic']['recall_at_5']<1) or (confidence(r,calibrator)>=calibrator['threshold'] and not r['top_relevant'])]
    report={'status':'frozen','version':'search-evaluation-v2','retriever_name':'MiniLM q8 + related threads','contract':contract,'corpus_sha256':corpus_hash,'index_sha256':digest(index_path),'provenance':search.corpus('v2')[0]['provenance'],'frozen':frozen,'policy_freeze_sha256':digest(policy_path),'policy':'Raw cosine orders leading discussions; explicit public related_ids expand supporting threads, capped at five. Confidence uses the unrelated-runner margin. Query relevance labels are never retrieval inputs. Ranking is measured before abstention; no-answer queries are excluded. Development/calibration policy froze before new test groups were ranked.','splits':summary,'test_slices':slices,'threshold':calibrator['threshold'],'gate':{'passed':passed,'minimum_recall_at_5':.85,'requires_paraphrase_improvement':True,'calibration_qualified':calibrator['calibration_qualified']},'latency':{'scope':'Offline host evidence, not browser or Wasmer latency; stdlib ranking and Node CPU q8.','encoder_runtime':encoded['runtime'],'model_load_ms':encoded['model_load_ms'],'query_embedding':search.timing_summary([q['duration_ms'] for q in encoded_queries]),'semantic_rank':search.timing_summary([r['semantic_ms'] for r in rows]),'bm25_rank':search.timing_summary([r['keyword_ms'] for r in rows])},'failure_examples':[{'query_id':r['query']['id'],'query':r['query']['text'],'relevance':r['query']['relevance'],'semantic_ids':r['semantic_ids'],'cosine_ids':r['cosine_ids'],'bm25_ids':r['bm25_ids'],'confidence':confidence(r,calibrator),'accepted':confidence(r,calibrator)>=calibrator['threshold']} for r in failures[:10]],'test_predictions':[{'query_id':r['query']['id'],'semantic_ids':r['semantic_ids'],'cosine_ids':r['cosine_ids'],'bm25_ids':r['bm25_ids'],'confidence':confidence(r,calibrator)} for r in test]}
    write(report_path,report)
    print(json.dumps({'test':summary['test'],'paraphrase':slices['paraphrase'],'gate_passed':passed},indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--verify',action='store_true'); main(parser.parse_args().verify)
