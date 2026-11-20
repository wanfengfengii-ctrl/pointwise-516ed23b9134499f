# 恒浦计量室双工位复测

恒浦计量室的两台参考台架各有零漂。中心分析员接班时，两站的原测库可能已关闭。质控员操作量具时只看得到表盘，按中心报告选择低档、高档或人工复测。

## 运行

使用 Python 3.11 和标准库。从项目根目录运行以下命令。控制台物化工程时提供 `check_project.py`。

```text
python3 -B check_project.py
python3 -B -m reports.shift demo --sample samples/handover.json
python3 -B -m reports.shift incident --sample samples/handover.json
```

直接运行测试包可用 `python3 -B -m unittest discover -s tests -t . -v`。示例使用临时站库和中心库，输出根据实际签发、重开和领取得到的 JSON。`incident` 对照主样例的选档区间，出现区间差异时以非零状态退出并输出 `GEAR_SELECTION_MISMATCH`。

## 一天的交班

1. 试验员根据复测单为同批甲乙工位登记角色及三个坐标的物理跨度，中心保存同批名册。
2. 试验员提交原测名、参考偏差、单位、闭线性限制及本站零漂上下界。站库一次提交归一限制及原测出处，并把新修订设为现行。
3. 试验员按显式修订号冻结本站件。已发行件及其回执可按发行号领取。
4. 中心接纳两个固定封套，保留规范正文、中心件号和接纳回执。样例随后关闭站库并移开站源目录。
5. 分析员按两个中心件号及政策 `v1` 签发。质控员使用共同证据域、两档可用范围和人工复测段。
6. 晚班找到参考偏差勘误时，以父修订中的具名原测为依据提交替换。旧修订和旧件仍可领取，也可按旧修订再发行。
7. 中心将新乙件与原先指定的甲件配对，签发新的独立报告号。
8. 质控员在中心重开后按新旧报告号领取或导出，分别核对当时的父件、政策、区间和回执。

## Python 接口

`reports.shift.initialize_workspaces(root, specs)` 接受两个 `intake.batches.BatchSpec(batch, station, role, scales_um)`，角色为 `alpha` 和 `beta`。返回值提供 `open_station(role)` 和 `open_center()`。站库可直接用于 `with`，中心连接应用 `contextlib.closing` 关闭。也可分别调用站库、中心初始化及注册 API。重复初始化保留目录、现行指向和各历史定稿。同号重复登记须与原角色、跨度或站点名册一致。写接口自主管理事务，用空闲连接调用。

| 公开入口 | 参数与结果 |
| --- | --- |
| `intake.revisions.record` | `store, batch, station, measurements`，可选关键字 `drift`、`parent_revision`。返回原测与归一限制齐全的 `MeasureRevision`。初录须提交 `drift`，勘误可继承父界。勘误允许从指定的同批同站历史修订派生。 |
| `release.issue.freeze` | `store, batch, station, revision_id`。返回 `(StationPiece, IssueReceipt)`，可用 `release.catalog.reclaim_issue(store, issue_id)` 重领。 |
| `exchange.admission.accept` | `center, batch, body`。`body` 由 `canonical_envelope_body(seal_piece(piece))` 生成，返回带接纳回执的 `AcceptedPiece`。 |
| `reports.publish.publish` | `center, batch, first_id, second_id, policy_name`。输入两个中心件号，返回带甲乙角色顺序父件和回执的 `SignedReport`。 |
| `reports.retrieve.read` | `center, report_id`。领取已定稿的 `SignedReport`。同参数的 `reports.export.export_report` 返回规范 JSON 文本。 |

测据项由 `name`、`value`、`unit`、`constraints` 构成。`value` 是归一到 q 坐标的参考记录，实际可行性由 `constraints` 给出。每条限制提供三个位置依次为 p、q、t 的 `coefficients` 和 `units`、关系 `op`（`=`、`<=` 或 `>=`）及 `bound`。例如工位按相同归一尺度记录 `q−p=t` 时，系数为 `[-1, 1, -1]`，三个单位均为 `normalized`，关系为 `=`，右界为 `0`。空限制列表允许录入仅由坐标和零漂边界限定的测据。`drift` 由 `lower`、`upper` 和 `unit` 构成。物理单位支持 `nm`、`um`、`μm`、`µm`、`mm`。批次跨度 `scales_um` 以微米给出，物理坐标在该单位下的数值为归一坐标乘以换算后的跨度。系数和界值按此等价换算。精确数可用整数、Fraction、整数比字符串或有限十进制字符串。

## 计算与交换口径

p 和 q 均在闭区间 [0,1]，t 是本站独立、有界的私有变量。发行时对同一个 t 的全部上下界求相容关系。站件正文用精确半平面和隐含单位方形表达二维闭关系，无解用 `empty: true` 和空半平面列表表示。线段与孤点保留。V1 封套固定发行号、批站角色、父修订和正文。接纳核对名册与站点编号命名空间，并锁定规范正文。重复提交同号同规范内容可重领原中心件和凭据。原测、原单位和零漂留在站库。

中心将两个件约束施加到同一个 `(p,q)`，按 p 输出共同证据域。对每个有证据的 p，低档扣除 0，高档扣除 1。每档须使该 p 截面内所有 q 的绝对残差至多 1/2，等号通过。无安全档的证据读数进入人工复测，证据域以外无共同证据。区间编码为 `[左端点, 右端点, 左闭, 右闭]`，端点是精确有理字符串，区间组按升序输出。合法无共同证据的发布结果有四组空区间和正常回执。

样例甲件限定 `q−p=t`、`|t|≤1/4`，乙件为单位方形。此时低档可用 [0,1/4]，高档可用 [3/4,1]，人工复测为 (1/4,3/4)。乙件勘误到 `q=p` 后，两档在 1/2 交接且该点同时可用。历史报告仍按之前的父件、政策和回执领取。样例使用固定测据，独立发行和发布分配独立编号。

## 拒绝与恢复

格式和归属校验失败以 `ValueError` 报告，缺少已登记对象以 `LookupError` 报告，SQLite 写入错误保留原异常。错父修订不改变现行指向。缺修订不发行，错批、错角色、同号异正文来件不新增接纳，缺件、混批及非法政策不生成报告。写失败回滚本次成果和回执。领取与导出按报告号读提交快照，未发布号码返回未找到。原回归用隔离目录、实际站件和 SQLite 触发器核对断源、空结果、退化区间、勘误与提交恢复。
