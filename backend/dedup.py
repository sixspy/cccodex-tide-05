"""批内重行识别与取舍的纯函数模块。

术语：
- 重行：两行（或更多）站码与观测时刻完全相同的行。
- 行号缺失的行不参与比较，按单行处理。
- 取舍两种：
  * KEEP_FIRST（留行）：行号最小的一行保留，其余进跳过队列；
  * REJECT_BOTH（双拒）：同一重行组里的每一行都不入库，进跳过队列。
"""

from collections import defaultdict

# 批内取舍名（写入策略簿、批次、跳过队列）
KEEP_FIRST = "留行"
REJECT_BOTH = "双拒"
DECISIONS = (KEEP_FIRST, REJECT_BOTH)

# 行级去向
DISP_SINGLE = "单行"            # 不构成重行，后续按跨批去重处理
DISP_KEPT = "保留"              # 重行组里行号最小的一行（留行取舍）
DISP_SKIPPED_DUP = "跳过重行"   # 重行组里被跳过的行（留行取舍）
DISP_DOUBLE_REJECT = "双拒"     # 双拒取舍，整组都不入库

# 跳过原因
SKIP_DOUBLE_REJECT = "批内重行双拒"
SKIP_KEPT_ELSEWHERE = "批内重行，保留行号更小的一行"
SKIP_ALREADY_LANDED = "这个站这个时刻已经落过库"


def find_duplicate_groups(rows):
    """按 (站码, 时刻) 分组，只返回成员数 >= 2 的组。

    rows: list[dict]，每个 dict 至少含
        line_no（int | None，None 表示行号缺失）、
        station_code、observed_at（datetime）。
    返回 list[list[int]]，每项是组内行在 rows 中的下标，
    组内按 line_no 升序；组间按首个行号、站码排序。
    行号缺失的行不会出现在任何组里。
    """
    buckets = defaultdict(list)
    for idx, row in enumerate(rows):
        if row.get("line_no") is None:
            continue  # 行号缺失的行不参与比较
        key = (row["station_code"], row["observed_at"])
        buckets[key].append(idx)
    groups = []
    for indexes in buckets.values():
        if len(indexes) >= 2:
            indexes.sort(key=lambda i: rows[i]["line_no"])
            groups.append(indexes)
    groups.sort(key=lambda group: (rows[group[0]]["line_no"], rows[group[0]]["station_code"]))
    return groups


def classify_rows(rows, decision):
    """给每一行标注批内去向。

    返回 dict:
      dispositions: {行下标: 去向常量}；
      duplicate_groups: find_duplicate_groups 的结果；
      kept_indexes: 留行取舍下应保留的行下标；
      rejected_indexes: 双拒取舍下整组拒掉的行下标；
      skipped_indexes: 留行取舍下进跳过队列的行下标。
    """
    if decision not in DECISIONS:
        raise ValueError(f"未知取舍: {decision!r}，只允许 {DECISIONS}")

    dispositions = {idx: DISP_SINGLE for idx in range(len(rows))}
    groups = find_duplicate_groups(rows)
    kept_indexes, rejected_indexes, skipped_indexes = [], [], []

    for indexes in groups:
        if decision == KEEP_FIRST:
            keep_idx = indexes[0]
            dispositions[keep_idx] = DISP_KEPT
            kept_indexes.append(keep_idx)
            for idx in indexes[1:]:
                dispositions[idx] = DISP_SKIPPED_DUP
                skipped_indexes.append(idx)
        else:  # REJECT_BOTH
            for idx in indexes:
                dispositions[idx] = DISP_DOUBLE_REJECT
                rejected_indexes.append(idx)

    return {
        "dispositions": dispositions,
        "duplicate_groups": groups,
        "kept_indexes": kept_indexes,
        "rejected_indexes": rejected_indexes,
        "skipped_indexes": skipped_indexes,
    }
