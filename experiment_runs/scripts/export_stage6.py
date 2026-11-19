"""Export report bundle without duplicating the large, Git-delivered replicate arrays."""
import argparse,shutil,zipfile
from p6_common import *

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--destination',type=Path,required=True);parser.add_argument('--receipt',type=Path);args=parser.parse_args()
    assert load(OUT/'final_acceptance.json')['passed']
    dest=args.destination;dest.mkdir(parents=True,exist_ok=True)
    mapping={'P6_REPORT.md':'P6第七阶段实验报告.md','FINAL_RESULTS.md':'P0-P6最终结果摘要.md','REPRODUCE.md':'P6复现实验指南.md','final_acceptance.json':'P6最终验收.json'}
    exported=[]
    for source,target in mapping.items():
        if source.endswith('.md'):
            content=(OUT/source).read_text(encoding='utf-8')
            for original,local in mapping.items():content=content.replace(']('+original+')',']('+local+')')
            content=content.replace('](../../../protocol/P6_STATISTICS_V1.md)','](https://github.com/Liu-Jiye/Online-Resilience-Reconstruction-of-Satellite-Information-Distribution-Task-Schemes/blob/main/experiment_runs/protocol/P6_STATISTICS_V1.md)')
            (dest/target).write_text(content,encoding='utf-8')
        else:shutil.copyfile(OUT/source,dest/target)
        exported.append(dest/target)
    bundle=dest/'P6阶段报告_汇总表_图表.zip'
    selected=[]
    for path in OUT.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(OUT)
        if relative.parts[0] in ['replicates','raw_audit']:continue
        if relative.parts[0]=='resampling' and path.suffix=='.npz':continue
        selected.append((path,relative.as_posix()))
    for path in sorted((ROOT/'scripts').glob('*.py')):
        if 'stage6' in path.name or path.name.startswith('p6_'):selected.append((path,'code/'+path.name))
    selected += [(ROOT/'tests/test_p6_statistics.py','code/test_p6_statistics.py'),(ROOT/'protocol/P6_STATISTICS_V1.md','P6_STATISTICS_V1.md')]
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path,name in selected:archive.write(path,name)
        archive.writestr('PACKAGE_CONTENTS.md','# P6 阅读包\n\n包含报告、全部汇总/分层/配对表、九张图及源码、验收与复现说明。完整10,000重复数组、整数重采计数及逐调用原始复核表已直接交付Git仓库experiment_runs/reports/p6/P6-20261118；本阅读包不重复这些大文件。原P4/P5原始证据保留原路径。\n')
        if args.receipt:archive.write(args.receipt,'Git_delivery_receipt.json')
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None;count=len(archive.infolist())
    exported.append(bundle)
    if args.receipt:
        target=dest/'P6_Git_delivery_receipt.json'
        if args.receipt.resolve()!=target.resolve():shutil.copyfile(args.receipt,target)
        exported.append(target)
    result=dict(passed=True,zip_integrity_passed=True,bundle_files=count,bundle_scope='Report/tables/figures/code/acceptance; full replicate arrays and raw audit directly in Git, omitted from convenience ZIP',
        files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in exported})
    save(dest/'P6导出材料清单.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
