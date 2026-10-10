import json, re

src = open('heat-report.html', encoding='utf-8').read()
data = json.loads(re.search(r'const DATA = (\{.*\});', src).group(1))
meta = json.loads(re.search(r'const META = (\{.*\});', src).group(1))

W_MOVE, W_CLICK, W_SCROLL = 0.01, 4, 2
def meq(r): return r[4]*W_MOVE + r[5]*W_CLICK + r[6]*W_SCROLL

NIGHT = [22,23,0,1,2,3,4,5]
MORN  = [5,6,7,8,9]

hour = [0]*24
dow = [0]*7
dowc = [0]*7
all_equiv = 0
day_keys = sorted(data.keys())
for k in day_keys:
    d = [int(x) for x in k.split('-')]
    import datetime
    wd = datetime.date(d[0],d[1],d[2]).weekday()      # Python: 周一=0..周日=6
    js_getday = (wd + 1) % 7                           # JS getDay(): 周日=0..周六=6
    di = (js_getday + 6) % 7                           # 模板口径: 周一=0..周日=6
    for r in data[k]:
        h = r[0]//60
        if 0 <= h < 24:
            hour[h] += r[1] + meq(r)
    day_equiv = sum(r[1]+meq(r) for r in data[k])
    all_equiv += day_equiv
    dow[di] += day_equiv
    dowc[di] += 1

night_sum = sum(hour[h] for h in NIGHT)
morn_sum = sum(hour[h] for h in MORN)
wk_avg = (dow[0]+dow[1]+dow[2]+dow[3]+dow[4])/max(1, dowc[0]+dowc[1]+dowc[2]+dowc[3]+dowc[4])
we_avg = (dow[5]+dow[6])/max(1, dowc[5]+dowc[6])

print('DATA 天数(DAY_KEYS.length) =', len(day_keys), ' META.days =', meta.get('days'))
print('日期范围 =', meta.get('range'))
print('TOTAL_EQUIV(全周期当量) = %.0f' % all_equiv)
print()
print('判定阈值实测：')
print('  周末/工作日比 = %.3f  (触发周末战士需 > 1.18 且周末有数据)' % (we_avg/wk_avg if wk_avg else 9))
print('  nightSum/TOTAL = %.3f  (触发夜猫子需 > 0.28)' % (night_sum/all_equiv))
print('  mornSum/TOTAL  = %.3f  (触发早起鸟需 > 0.20)' % (morn_sum/all_equiv))
print()
if we_avg > wk_avg*1.18 and (dowc[5]+dowc[6])>0:
    p='周末战士'
elif night_sum/all_equiv > 0.28:
    p='夜猫子'
elif morn_sum/all_equiv > 0.20:
    p='早起鸟'
else:
    p='规律型'
print('→ 命中分支：', p)
print('→ 渲染文案：', '你这 %d 天，是个「%s」' % (len(day_keys), p))
