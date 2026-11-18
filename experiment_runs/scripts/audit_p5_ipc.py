"""Pinned PDDL structural applicability audit; no planner performance claims.

Raw third-party source remains outside the deliverable repository pending license.
The receipt contains URLs, hashes, counts, and structural metadata only.
"""
import os,re,urllib.request,time,subprocess
from collections import Counter,defaultdict
from p5_common import *

COMMIT='cf19edf7c53d1540ddbb396c642595e0926ee552'
REPO='potassco/pddl-instances'
DOMAINS=['satellite-time-automatic','satellite-time-simple-automatic']

def fetch(url,path):
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        req=urllib.request.Request(url,headers={'User-Agent':'Satellite-P5-reproducible-audit'})
        if url.startswith('https://api.github.com/'):
            data=subprocess.run(['gh','api',url.removeprefix('https://api.github.com/')],check=True,capture_output=True).stdout
        else:
            with urllib.request.urlopen(req,timeout=90) as r:data=r.read()
        path.write_bytes(data)
    return path.read_bytes()

def parse(raw):
    tokens=re.findall(r'\(|\)|[^\s()]+',re.sub(r';[^\n]*','',raw.decode('utf-8-sig')).lower())
    stack=[];root=[];current=root
    for t in tokens:
        if t=='(':n=[];current.append(n);stack.append(current);current=n
        elif t==')':
            if not stack:raise ValueError('unbalanced closing parenthesis')
            current=stack.pop()
        else:current.append(t)
    if stack or len(root)!=1 or root[0][0]!='define':raise ValueError('not one balanced define form')
    return root[0],tokens

def main():
    cache=Path(os.environ['P5_IPC_CACHE']);treeurl=f'https://api.github.com/repos/{REPO}/git/trees/{COMMIT}?recursive=1'
    tree=json.loads(fetch(treeurl,cache/'tree.json'))['tree'];rows=[];errors=[]
    licenses=[x['path'] for x in tree if x['type']=='blob' and re.search(r'(^|/)(license|copying|copyright)(\.|$)',x['path'],re.I)]
    groups=defaultdict(list);normalized=defaultdict(list)
    for domain in DOMAINS:
        prefix='ipc-2002/domains/'+domain+'/'
        paths=[x['path'] for x in tree if x['type']=='blob' and x['path'].endswith('.pddl') and
            (x['path']==prefix+'domain.pddl' or x['path'].startswith(prefix+'instances/'))]
        for path in sorted(paths):
            url=f'https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}'
            raw=fetch(url,cache/path);row=dict(path=path,url=url,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),domain_directory=domain)
            try:
                ast,tokens=parse(raw);is_domain=ast[1][0]=='domain';sections={x[0]:x[1:] for x in ast[2:] if isinstance(x,list) and x}
                row.update(parsed=True,kind='domain' if is_domain else 'problem',declared_name=ast[1][1],requirements=sections.get(':requirements',[]),
                    durative_actions=sum(isinstance(x,list) and bool(x) and x[0]==':durative-action' for x in ast),
                    objects_tokens=len(sections.get(':objects',[])),init_forms=len(sections.get(':init',[])),
                    numeric_operators={t:tokens.count(t) for t in ('=','increase','decrease','assign','*','/','>=','<=') if t in tokens})
                exact=hashlib.sha256(' '.join(tokens).encode()).hexdigest();row['normalized_token_sha256']=exact
                if not is_domain:
                    for section in (':objects',':goal',':init'):
                        row[section[1:]+'_sha256']=hashlib.sha256(json.dumps(sections.get(section,[]),separators=(',',':')).encode()).hexdigest()
                    normalized[exact].append(path)
                    # Remove only declared problem/domain identifiers. Preserve
                    # all object names, initial facts, goals and metric terms.
                    ast[1][1]='__problem__'
                    for x in ast:
                        if isinstance(x,list) and x and x[0]==':domain':x[1]='__domain__'
                    h=hashlib.sha256(json.dumps(ast,separators=(',',':')).encode()).hexdigest()
                    row['identifier_normalized_sha256']=h;groups[h].append(path)
            except Exception as e:row.update(parsed=False,error=str(e));errors.append(path)
            rows.append(row)
    problem=[r for r in rows if r.get('kind')=='problem'];domainrows=[r for r in rows if r.get('kind')=='domain']
    pairs=[]
    for number in range(1,21):
        a,b=[next(r for r in problem if r['path']==f'ipc-2002/domains/{d}/instances/instance-{number}.pddl') for d in DOMAINS]
        pairs.append(dict(instance_number=number,paths=[a['path'],b['path']],same_objects=a['objects_sha256']==b['objects_sha256'],same_goals=a['goal_sha256']==b['goal_sha256'],same_initial_facts=a['init_sha256']==b['init_sha256']))
    result=dict(commit=COMMIT,source_repository=f'https://github.com/{REPO}',tree_url=treeurl,files=rows,cross_directory_pairs=pairs,
        independence_warning='Distinct PDDL text does not establish independent task populations; both variants are IPC2002 Satellite and number-matched relationships are listed explicitly',
        counts=dict(domain_files=len(domainrows),problem_files=len(problem),parsed_problem_files=sum(r['parsed'] for r in problem),parse_failures=len(errors),
            unique_problem_token_streams=len(normalized),unique_problems_after_identifier_normalization=len(groups)),
        exact_normalized_duplicate_groups=[g for g in normalized.values() if len(g)>1],
        identifier_normalized_duplicate_groups=[g for g in groups.values() if len(g)>1],
        license_audit=dict(repository_license_paths=licenses,redistributed_raw_pddl=False,raw_source_policy='cache outside repository; URLs and SHA256 only',
            conclusion='No license permission inferred from public availability; source audit only'),
        applicability=dict(parse_scope='balanced S-expression and structural sections; not semantic type/action validation',
            temporal_planner_adapter=False,temporal_plan_validator_adapter=False,initial_solve_attempts='not_run',initial_solvable_count='not_run',
            validated_initial_plans='not_run',performance_events='not_run',reason='Full durative actions, numeric state and goal semantics have no implemented adapter; user approved applicability-only branch',
            flattened_isl_surrogate_used=False),errors=errors)
    assert len(problem)==40 and len(domainrows)==2 and not errors
    save(OUT/'ipc/applicability_audit.json',result)
    print(json.dumps(dict(counts=result['counts'],license_paths=licenses,performance='not_run')))

if __name__=='__main__':main()
