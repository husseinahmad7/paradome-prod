"""Expand explicit public thread links; query labels never enter retrieval."""
def expand_related(scored, limit=5):
    by_id={doc['id']:(doc,score) for doc,score in scored}
    output=[]; seen=set()
    for doc,score in scored:
        if doc['id'] in seen:
            continue
        output.append((doc,score)); seen.add(doc['id'])
        if len(output)==limit:
            break
        for related_id in doc.get('related_ids',[]):
            if related_id in by_id and related_id not in seen:
                output.append(by_id[related_id]); seen.add(related_id)
                if len(output)==limit:
                    break
        if len(output)==limit:
            break
    return output

def unrelated_margin(scored):
    first,score=scored[0]
    related=set(first.get('related_ids',[]))
    runner=next((other_score for doc,other_score in scored[1:] if doc['id'] not in related),score)
    return score-runner
