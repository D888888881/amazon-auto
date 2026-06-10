import asyncio
import json
import os
import re
import shutil
from pathlib import Path

import aiohttp
import pandas as pd
import numpy as np
from async_read_config import read_main, read_taobao_config
import async_sif_api
from async_advertisement_api import advertisement_main, fetch_multiple_asins, fetch_multiple_asins_totalUnits
from typing import List, Dict, Any, Optional
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment
from async_image_search_api import async_price_info_main
from async_fba_api import async_fba_batch
from async_return_rale_api import fetch_refund_rate_for_path, prefetch_refund_rates_batch
from seller_account_guard import is_seller_account_banned_error
from shared_rate_limit import async_api_slot, env_max_concurrent
from taobao__m_h5_tk import get_taobao_tokens
from wizard_progress import emit_progress
# 本地数据根目录：相对本脚本所在目录的 file/，避免「在别的 cwd 运行脚本」时扫不到 Excel
# FILE_DATA_ROOT = Path(r"E:\py_projiect\auto_amazon_project\media\file")
SCRIPT_DIR = Path(__file__).resolve().parent
IMAGES_DIR = SCRIPT_DIR / "images"
FILE_DATA_ROOT = SCRIPT_DIR.parent.parent / "media" / "file"

# SIF 无 ASIN 数据时的广告指标默认值
SIF_DEFAULT_AD_CPC = 1.0
SIF_DEFAULT_AD_CLICKS = 100.0
SIF_DEFAULT_CONVERSION_RATE = 0.10  # 10%

# 其它接口缺数据时的 ROI 默认值（仍生成 ROI-US-pack.xlsx）
ROI_DEFAULT_UNIT_PURCHASE = 10.0
ROI_DEFAULT_FBA_FEE = 5.0
ROI_DEFAULT_REFUND_RATE = 10.0
ROI_DEFAULT_PRODUCT_PRICE = 29.99


def _positive_float_or_none(value) -> float | None:
    try:
        num = float(value)
        if num > 0:
            return num
    except (TypeError, ValueError):
        pass
    return None


def resolve_sif_ad_metrics(
    product_asin: str,
    asin_cpc_list: list,
    daily_orders: float,
) -> tuple[float, float, float]:
    """
    从 SIF 聚合结果解析广告 cpc / 转化率 / 点击数。
    字段为空、None 或 <=0 时使用默认值，避免 ROI-US-pack 无法生成。
    """
    asin_cpc_dict: dict[str, dict] = {}
    cpc_items = asin_cpc_list if isinstance(asin_cpc_list, list) else []
    for item in cpc_items:
        if not isinstance(item, dict):
            continue
        for asin_key, info in item.items():
            if not isinstance(info, dict):
                continue
            key = str(asin_key).strip().upper()
            cpc_info = info.get('cpc') or {}
            cpc_median = cpc_info.get('median') if isinstance(cpc_info, dict) else None
            asin_cpc_dict[key] = {
                'cpc_median': cpc_median,
                'clickPurchaseRatio': info.get('clickPurchaseRatio'),
            }

    product_key = str(product_asin).strip().upper()
    cpc_info = asin_cpc_dict.get(product_key, {})
    used_defaults = False

    ad_cpc = _positive_float_or_none(cpc_info.get('cpc_median'))
    if ad_cpc is None:
        ad_cpc = SIF_DEFAULT_AD_CPC
        used_defaults = True

    conversion_rate = _positive_float_or_none(cpc_info.get('clickPurchaseRatio'))
    if conversion_rate is None:
        conversion_rate = SIF_DEFAULT_CONVERSION_RATE
        used_defaults = True

    if daily_orders > 0 and conversion_rate > 0:
        ad_clicks = daily_orders / conversion_rate * 0.5
    else:
        ad_clicks = None
    if ad_clicks is None or ad_clicks <= 0:
        ad_clicks = SIF_DEFAULT_AD_CLICKS
        used_defaults = True

    if used_defaults:
        print(
            f'ASIN {product_key} SIF 广告数据缺失，使用默认值：'
            f'cpc={ad_cpc}, 点击={ad_clicks}, 转化率={conversion_rate * 100:.0f}%'
        )

    return ad_cpc, conversion_rate, ad_clicks

# 卖家精灵导出 Excel 列名 -> 内部 API 风格字段（与 colum_mapping.json 中译名对齐）
COLUMN_MAPPING_EXCEL_TO_API = {
    "ASIN": "asin",
    "父ASIN": "parent",
    "SKU": "sku",
    "品牌": "brand",
    "品牌链接": "brandUrl",
    "搜索排名": "lqs",
    "商品标题": "title",
    "商品详情页链接": "asinUrl",
    "商品主图": "imageUrl",
    "类目路径": "nodeLabelPath",
    "节点标签路径": "nodeLabelPath",
    "节点路径": "nodeLabelPath",
    "大类目": "categoryName",
    "大类BSR": "bsrRank",
    "小类目": "bsrLabel",
    "小类BSR": "subcategories",
    "月销量": "totalUnits",
    "月销量增长率": "totalUnitsGrowth",
    "月销售额($)": "totalAmount",
    "子体销量": "fbaUnits",
    "子体销售额($)": "fbaAmount",
    "变体数": "variations",
    "价格($)": "price",
    "Prime价格($)": "primeExclusivePrice",
    "Coupon": "coupon",
    "Q&A数": "questions",
    "评分数": "reviews",
    "月新增评分数": "reviewsIncreasement",
    "评分": "rating",
    "留评率": "reviewsRate",
    "FBA($)": "fba",
    "毛利率": "profit",
    "上架时间": "availableDate",
    "上架天数": "availableDays",
    "LQS": "lqs",
    "卖家数": "sellers",
    "Best Seller标识": "bestSeller",
    "Amazon's Choice": "amazonChoice",
    "New Release标识": "newRelease",
    "商品重量": "weight",
    "商品尺寸": "dimensions",
    "包装重量": "pkgWeight",
    "包装尺寸": "pkgDimensions",
}


with open('config_file/colum_mapping.json', 'r', encoding='utf-8') as f:
    column_mapping = json.load(f)


# 验证/生成保存目录：优先使用显式 ASIN（与 file/{ASIN} 结构一致）
async def verify_path(
        keyword_dict: Optional[Dict[str, Any]] = None,
        keyword: Optional[str] = None,
        asin: Optional[str] = None,
) -> str:
    """
    返回文件保存的目录路径。

    规则：
    - 同时提供 asin 和 keyword：返回 FILE_DATA_ROOT / asin / keyword
    - 只提供 asin，不提供 keyword：返回 FILE_DATA_ROOT / asin
    - 只提供 keyword，且提供 keyword_dict：尝试匹配 ASIN，返回 FILE_DATA_ROOT / asin / keyword
    - 其他情况：返回默认目录 FILE_DATA_ROOT
    """
    base = Path(FILE_DATA_ROOT)

    # 1. 同时有 asin 和 keyword（最优先）
    if asin and keyword:
        path = base / asin / keyword

    # 2. 只有 asin，没有 keyword
    elif asin and not keyword:
        path = base / asin

    # 3. 只有 keyword，但提供了 keyword_dict 用于匹配 asin
    elif keyword and keyword_dict:
        matched_asin = None
        for key, values in keyword_dict.items():
            norm = values if isinstance(values, (list, tuple)) else [values]
            if keyword in norm:
                matched_asin = key
                break
        if matched_asin:
            path = base / matched_asin / keyword
        else:
            print(f"警告：关键词 '{keyword}' 未在 keyword_dict 中匹配到 ASIN，保存到默认目录。")
            path = base

    # 4. 其他情况
    else:
        path = base

    # 自动创建目录
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


# 清洗脏数据
async def save_cleaned_data_orign_to_excel(df: pd.DataFrame, keyword: str, asin: str,asin_info_dict:dict = None):
    """
    依赖字段（卖家精灵 Excel 映射后）：
    - brand / parent：去重；缺失则填空，避免 KeyError
    - price / totalUnits / reviews：清洗与分箱；缺失则转为 NaN
    - reviews：评论区间、sales_level
    - availableDate 等：导出多为日期字符串，非毫秒时间戳
    """

    df_deduplicated = df.copy()
    if "brand" not in df_deduplicated.columns:
        df_deduplicated["brand"] = ""
    if "parent" not in df_deduplicated.columns:
        df_deduplicated["parent"] = (
            df_deduplicated["asin"] if "asin" in df_deduplicated.columns else ""
        )
    for col in ("price", "totalUnits", "reviews"):
        if col not in df_deduplicated.columns:
            df_deduplicated[col] = np.nan
    df_deduplicated["brand"] = df_deduplicated["brand"].fillna("")
    df_deduplicated["parent"] = df_deduplicated["parent"].fillna("")
    df_deduplicated["totalUnits"] = pd.to_numeric(df_deduplicated["totalUnits"], errors="coerce")
    # df_deduplicated["reviews"] = pd.to_numeric(df_deduplicated["reviews"], errors="coerce")

    # 去重
    df_deduplicated = df_deduplicated.drop_duplicates(subset=["brand", "parent"]).copy()

    # 去除广告位
    before_count = len(df_deduplicated)
    mask = ~df_deduplicated['lqs'].astype(str).str.contains("广告位", na=False)
    df_deduplicated = df_deduplicated[mask].copy()
    after_count = len(df_deduplicated)
    print(f"已删除搜索排名包含'广告位'的行，删除前 {before_count} 行，剩余 {after_count} 行")

    # 价格清洗：基于当前 ASIN 价格过滤
    df_deduplicated['price'] = pd.to_numeric(df_deduplicated['price'], errors='coerce')
    df_deduplicated['totalUnits'] = pd.to_numeric(df_deduplicated['totalUnits'], errors='coerce')

    price_cleaning = df_deduplicated.dropna(subset=['price', 'totalUnits']).copy()
    asin_price = -1
    try:
        if asin_info_dict:
            asin_price = asin_info_dict.get('avg_price',0)
        else:
            # 获取 ASIN 基础价格（用于过滤上限）
            info_dict = await advertisement_main([asin])
            # print(info_dict)
            asin_price = info_dict[asin]["avg_price"]
            print(f"ASIN {asin} 价格：{asin_price}")
    except Exception as e:
        print('价格获取失败',e)

    # 过滤价格高于 asin_price * 1.3 的行
    upper_bound = asin_price * 1.3
    lower_bound = asin_price * 0.6
    price_cleaning_data = price_cleaning[
        (price_cleaning['price'] >= lower_bound) & (price_cleaning['price'] <= upper_bound)].copy()
    print(f"价格过滤后数据行数：{len(price_cleaning_data)}")
    print(price_cleaning_data['price'].describe())

    # # 删除无用列
    # columns_to_drop = [
    #     'New Release标识', 'A+页面', '视频介绍', 'SP广告', '品牌故事', '品牌广告', '7天促销', 'Best Seller标识',
    #     "Amazon's Choice", 'CPF绿标', '评级'
    # ]
    # price_cleaning_data.drop(columns=columns_to_drop, inplace=True, errors='ignore')
    print(f"清洗后的数据行数：{len(price_cleaning_data)}")

    # 时间字段：API 为毫秒时间戳；Excel 多为日期或字符串
    time_fields = ["syncTime", "amzUnitDate", "updatedTime", "availableDate", "firstReviewDate"]
    for field in time_fields:
        if field not in price_cleaning_data.columns:
            continue
        col = price_cleaning_data[field]
        try:
            num = pd.to_numeric(col, errors="coerce")
            if num.notna().any() and (num.dropna() > 1e11).all():
                price_cleaning_data[field] = pd.to_datetime(num, unit="ms", errors="coerce").dt.strftime(
                    "%Y-%m-%d"
                )
            else:
                price_cleaning_data[field] = pd.to_datetime(col, errors="coerce").dt.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"<时间列格式化>{field}: {e}")

    # 定义 bins：最后一个值用很大的数或无穷大
    bins = [0, 30, 60, 100, 150, 200, np.inf]  # 或 1e10

    labels = ['0-30', '31-50', '51-100', '101-150', '151-200', '200以上']
    #
    # 使用 cut 进行分级
    price_cleaning_data['sales_level'] = pd.cut(price_cleaning_data['reviews'], bins=bins, labels=labels,
                                                right=True, include_lowest=True)
    # 列名中文化
    # price_cleaning_data_chinese = price_cleaning_data.rename(columns=column_mapping)

    # 4. 保存清洗后的数据源 Excel 文件
    output_dir = await verify_path(asin=asin, keyword=keyword)

    # 9. 确保保存目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 10. 保存 Excel
    output_path = os.path.join(output_dir, f'{keyword}_data_origin.xlsx')

    price_cleaning_data.to_excel(output_path, index=False)
    print(f"文件已保存至: {output_path}")
    return price_cleaning_data


# 整理出市场容量前五
async def save_top5_market_capacity_to_excel(price_cleaning_data: pd.DataFrame, keyword: str, asin: str):
    # 1. 确保销量列为数值，并去掉缺失值
    price_cleaning_data['totalUnits'] = pd.to_numeric(price_cleaning_data['totalUnits'], errors='coerce')
    price_cleaning_data = price_cleaning_data.dropna(subset=['totalUnits'])

    # 2. 按销量降序排序，取前5名
    top5 = price_cleaning_data.sort_values('totalUnits', ascending=False).head(5).copy()
    top5.reset_index(drop=True, inplace=True)

    if top5.empty:
        print(
            f"警告: ASIN {asin} 关键词「{keyword}」清洗后无有效月销量(totalUnits)，"
            f"跳过 top5 市场容量分析，目标月销记为 0。"
        )
        return 0.0

    # 3. 初始化新列
    top5['实际增长倍数'] = np.nan
    top5['是否1.3-1.5递增减'] = ''
    top5['模拟增长数'] = top5['totalUnits'].astype(float).copy()

    # 4. 计算实际增长倍数和判断
    for i in range(len(top5) - 1):
        current = top5.loc[i, 'totalUnits']
        next_val = top5.loc[i + 1, 'totalUnits']
        if next_val > 0:
            ratio = current / next_val
            top5.loc[i, '实际增长倍数'] = round(ratio, 2)  # 保留两位小数
            if 1.3 <= ratio <= 1.5:
                top5.loc[i, '是否1.3-1.5递增减'] = '是'
            else:
                top5.loc[i, '是否1.3-1.5递增减'] = '否'
        else:
            top5.loc[i, '实际增长倍数'] = np.nan
            top5.loc[i, '是否1.3-1.5递增减'] = '否'
    if len(top5) > 0:
        top5.loc[len(top5) - 1, '实际增长倍数'] = np.nan
        top5.loc[len(top5) - 1, '是否1.3-1.5递增减'] = '-'

    # 5. 按新规则计算模拟增长数（以第二名为基准）
    if len(top5) >= 2:
        second_sales = top5.loc[1, 'totalUnits']
        top5.loc[0, '模拟增长数'] = second_sales * 1.5
        top5.loc[1, '模拟增长数'] = second_sales
        for i in range(2, len(top5)):
            top5.loc[i, '模拟增长数'] = second_sales / (1.5 ** (i - 1))
    else:
        # 如果只有一条数据，模拟增长数保持原销量
        pass

    # 5.1 模拟增长数保留两位小数
    top5['模拟增长数'] = top5['模拟增长数'].round(2)

    # 6. 全局统计值（站内月销上限 = 第一名实际销量，目标月销 = 上限/3）
    top_actual = top5.loc[0, '模拟增长数']
    total_upper_limit = round(top_actual, 2)  # 保留两位小数
    target_monthly_sales = round(total_upper_limit / 3, 2)  # 保留两位小数

    # 7. 构建明细表并重命名
    detail_df = top5[['totalUnits', '模拟增长数', '实际增长倍数', '是否1.3-1.5递增减']].copy()
    detail_df.rename(columns={'totalUnits': '月销'}, inplace=True)

    # 8. 添加全局统计列（只在第一行显示）
    final_df = detail_df.copy()
    final_df['站内月销上限'] = ''
    final_df['目标月销'] = ''
    final_df.loc[0, '站内月销上限'] = total_upper_limit
    final_df.loc[0, '目标月销'] = target_monthly_sales

    output_dir = await verify_path(asin=asin, keyword=keyword)

    # 9. 确保保存目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 10. 保存 Excel
    output_path = os.path.join(output_dir, f'{keyword}_top5_market_capacity.xlsx')
    final_df.to_excel(output_path, index=False)
    print(f"分析结果已保存为：{output_path}")

    # 11. 控制台输出
    print("前五名分析结果：")
    print(final_df.to_string(index=False))
    return target_monthly_sales


# 分析出区间前五数据
async def save_review_interval_analysis_to_excel(df: pd.DataFrame, keyword: str, asin: str):
    """
    对评论进行区间分级，计算每个区间月销前五的平均值，运营难度，并保存结果。
    返回: dict {'区间': list, '平均销量': list, '运营难度': list}
    """
    # 1. 确保评论列为数值，并去除缺失值
    df['reviews'] = pd.to_numeric(df['reviews'], errors='coerce')
    df = df.dropna(subset=['reviews', 'totalUnits']).copy()

    # 2. 定义评论区间
    bins = [0, 30, 50, 100, 200, np.inf]
    labels = ['0-30', '31-50', '51-100', '101-200', '200以上']
    df['评论区间'] = pd.cut(df['reviews'], bins=bins, labels=labels, right=True, include_lowest=True)

    # 3. 计算全量数据月销量前五的平均值（作为分母）
    top5_overall_sales = df.nlargest(5, 'totalUnits')['totalUnits']
    overall_avg_top5 = top5_overall_sales.mean()

    # 4. 计算每个区间月销前五的平均值
    interval_stats = []
    for interval in labels:
        group = df[df['评论区间'] == interval]
        if len(group) == 0:
            avg_sales = 0
        else:
            top5_sales = group.nlargest(5, 'totalUnits')['totalUnits']
            avg_sales = top5_sales.mean()
        interval_stats.append({'区间': interval, '平均销量': avg_sales})

    result_df = pd.DataFrame(interval_stats)

    # 5. 计算运营难度（百分比，分母为 overall_avg_top5）
    if overall_avg_top5 != 0:
        result_df['运营难度'] = (result_df['平均销量'] / overall_avg_top5 * 100).round(3).astype(str) + '%'
    else:
        result_df['运营难度'] = '0.000%'

    # 6. 定义难度标签函数，作为注释1列
    def difficulty_label(percent_str):
        try:
            percent = float(percent_str.replace('%', ''))
        except:
            return '-'
        if percent < 10:
            return '困难'
        elif percent <= 15:
            return '适中'
        else:
            return '简单'

    result_df['注释1'] = result_df['运营难度'].apply(difficulty_label)

    # 7. 调整主体部分列顺序
    result_df = result_df[['区间', '平均销量', '运营难度', '注释1']]

    # ========== 构建注释行（放在数据行之后） ==========
    comment_row = pd.DataFrame({
        '区间': [''],
        '平均销量': [''],
        '运营难度': [''],
        '注释1': [''],
        '注释2': ['和评论关系不大，非标产品居多，主要看产品'],
        '参照': ['1、低于10%=困难  2、10%-15%=适中  3、大于15%=简单']
    })

    # ========== 构建汇总行 ==========
    summary_row = pd.DataFrame({
        '区间': ['自然排名最高的五个产品的平均值 销量：'],
        '平均销量': [overall_avg_top5],
        '运营难度': [''],
        '注释1': [''],
        '注释2': [''],
        '参照': ['']
    })

    # 由于主体部分缺少注释2和参照列，concat时会自动添加，对应行填充NaN
    final_df = pd.concat([result_df, comment_row, summary_row], ignore_index=True)

    # 确保最终列顺序
    final_df = final_df[['区间', '平均销量', '运营难度', '注释1', '注释2', '参照']]

    # 保存 Excel
    output_dir = await verify_path(asin=asin, keyword=keyword)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{keyword}_review_interval_analysis.xlsx')
    final_df.to_excel(output_path, index=False)
    print(f"评论区间前五分析已保存至: {output_path}")

    print("\n评论区间分析结果预览：")
    print(final_df.to_string(index=False))

    # ========== 返回字典格式 ==========
    return {
        '区间': result_df['区间'].tolist(),
        '平均销量': result_df['平均销量'].tolist(),
        '运营难度': result_df['运营难度'].tolist()
    }


async def save_ad_efficiency_table(
        clean_data: pd.DataFrame,
        keyword: str,
        target_asin: str,
):
    """
    保存广告效率表：
    - 广告词数量/图片/均价/均评：来自 advertisement_main
    - 父体销量 totalUnits：优先来自 clean_data（按 asin 匹配/聚合）；
      若 target_asin 在 clean_data 中缺失，则回退到 fetch_multiple_asins_totalUnits 获取。
    将排名注释放在右侧区域顶部。
    target_asin：当前分析对应的 ASIN（与 file/{ASIN} 一致）。
    """
    # ==================== 1. 确定当前 ASIN ====================
    current_asin = target_asin.strip().upper() if target_asin else None

    # ==================== 2. 获取 ASIN 列表 ====================
    asin_list = clean_data['asin'].dropna().unique().tolist()
    if current_asin and current_asin not in asin_list:
        print(f"警告：当前 ASIN {current_asin} 不在清洗数据中，将临时添加以便获取广告词数据。")
        asin_list.append(current_asin)

    # ==================== 3. 获取广告词数据（不含 totalUnits） ====================
    try:
        ads_result = await advertisement_main(asin_list, max_concurrent=1)
        print("广告词数据示例：", list(ads_result.items())[:3])
    except Exception as e:
        print(f"获取广告词数据失败：{e}")
        ads_result = {}

    # ==================== 4. 从 clean_data 构建 asin -> totalUnits 映射 ====================
    total_units_by_asin = {}
    if "asin" in clean_data.columns and "totalUnits" in clean_data.columns:
        tmp = clean_data[["asin", "totalUnits"]].copy()
        tmp["asin"] = tmp["asin"].astype(str).str.strip().str.upper()
        tmp["totalUnits"] = pd.to_numeric(tmp["totalUnits"], errors="coerce")
        # 同一个 asin 可能多行：取最大值更稳妥（避免某行缺失导致取到 0/NaN）
        total_units_by_asin = (
            tmp.dropna(subset=["asin"])
            .groupby("asin")["totalUnits"]
            .max()
            .to_dict()
        )

    # target_asin 在 clean_data 无销量时，回退到接口获取
    need_fetch_target_units = False
    if current_asin:
        if current_asin not in total_units_by_asin:
            need_fetch_target_units = True
        else:
            v = total_units_by_asin.get(current_asin)
            if pd.isna(v):
                need_fetch_target_units = True

    if need_fetch_target_units:
        try:
            target_asin_total_units = await fetch_multiple_asins_totalUnits([current_asin], 1)
            # 期望结构：{'B0FWJ8HNCB': {'totalUnits': 2242, 'salesTrend': '...'}}
            fetched = (target_asin_total_units or {}).get(current_asin, {}).get("totalUnits")
            fetched = pd.to_numeric(fetched, errors="coerce")
            if not pd.isna(fetched):
                total_units_by_asin[current_asin] = float(fetched)
                print(f"target_asin={current_asin} 的 totalUnits 回退获取成功: {fetched}")
            else:
                print(f"警告：target_asin={current_asin} 回退接口未返回有效 totalUnits")
        except Exception as e:
            print(f"警告：回退获取 target_asin totalUnits 失败: {e}")

    # ==================== 5. 构建 DataFrame（广告字段来自 ads_result） ====================
    rows = []
    total_units1 = -1
    ad_words1 = -1
    for asin in asin_list:
        data = ads_result.get(asin)
        if not data:
            continue
        asin_norm = str(asin).strip().upper()
        image_url = data.get("imageUrl", "")
        price = data.get("avg_price", data.get("price", 0))
        reviews = data.get("avg_reviews", data.get("reviews", 0))
        total_units = total_units_by_asin.get(asin_norm, np.nan)
        ad_words = sum(data.get(k, 0) for k in ['ads', 'highly_rated', 'sponsor_video', 'sponsor_brand'])
        if asin == target_asin:
            total_units1 = total_units
            ad_words1 = ad_words
        ad_efficiency = total_units / ad_words if ad_words > 0 else np.nan

        rows.append({
            'imageUrl': image_url,
            'asin': asin,
            '广告词数量': ad_words,
            'totalUnits': total_units,
            'reviews': reviews,
            'price': price,
            '广告效率': ad_efficiency
        })

    if not rows:
        print("警告：没有有效的广告词数据，无法生成广告效率表")
        return -1

    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values('广告效率', ascending=False, na_position='last').reset_index(drop=True)

    # ==================== 6. 计算排名率 ====================
    ranking_note = ""
    ranking_percent = -1
    if current_asin:
        valid_df = result_df[result_df["广告词数量"] > 0].reset_index(drop=True)
        valid_df["_asin_norm"] = valid_df["asin"].astype(str).str.strip().str.upper()
        if current_asin in valid_df["_asin_norm"].values:
            rank = valid_df[valid_df["_asin_norm"] == current_asin].index[0] + 1
            total_valid = len(valid_df)
            ranking_percent = (rank / total_valid) * 100 if total_valid > 0 else 0

            if ranking_percent <= 70:
                ranking_note = f"当前产品在排序中处于{ranking_percent:.1f}%的位置，排名小于70%，相对好运营"
            else:
                ranking_note = f"当前产品在排序中处于{ranking_percent:.1f}%的位置，排名大于等于70%，运营难度较大"
        else:
            ranking_note = "当前产品广告词数量为0，无法计算广告效率排名"

    # ==================== 7. 构建结果 DataFrame ====================
    result_df = result_df[['imageUrl', 'asin', '广告词数量', 'totalUnits', 'reviews', 'price', '广告效率']].copy()
    result_df.rename(columns={
        'imageUrl': '图片',
        'asin': '链接',
        'totalUnits': '父体销量',
        'reviews': '评论数量',
        'price': '价格'
    }, inplace=True)

    # ==================== 8. 添加说明行（仅方法说明，不含排名注释） ====================
    notes = [
        "具体方法:",
        "1、找到最精准的关键词(建议用H10的Cerebro ASIN版),进去搜索结果页面",
        "2、把所有的产品打开,一个个去统计他们的父体销量,广告词数量,然后拿父体销量/广告词数量,得到广告效率,最后进行排序",
        "3、如果我们想做的这个产品在排序中处于70%以上,说明相对好运营"
    ]
    note_rows = []
    for note in notes:
        row = {col: '' for col in result_df.columns}
        row['图片'] = note
        note_rows.append(row)
    notes_df = pd.DataFrame(note_rows)
    final_df = pd.concat([result_df, notes_df], ignore_index=True)

    # ==================== 9. 直接保存 URL 文本（不下载图片） ====================
    output_dir = await verify_path(asin=target_asin, keyword=keyword)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{keyword}_ad_efficiency_table.xlsx')
    final_df.to_excel(output_path, index=False, engine='openpyxl')
    wb = load_workbook(output_path)
    ws = wb.active

    # ==================== 10. 高亮当前 ASIN 的链接 ====================
    if current_asin:
        yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        for row in range(2, ws.max_row + 1):
            cell = ws.cell(row=row, column=2)  # 链接列是第二列
            cv = str(cell.value).strip().upper() if cell.value is not None else ""
            if cv == current_asin:
                cell.fill = yellow_fill

    # ==================== 11. 将排名注释添加到右侧区域顶部 ====================
    if ranking_note:
        right_cols = [8, 9, 10]
        target_row = 5
        # 清空第5行右侧三列原有内容（可选）
        for col in right_cols:
            ws.cell(row=target_row, column=col).value = ''
        # 在右侧第一列写入注释
        note_cell = ws.cell(row=target_row, column=right_cols[0])
        note_cell.value = ranking_note
        note_cell.font = Font(size=26, bold=True)
        note_cell.alignment = Alignment(horizontal='center', vertical='center')
        # 设置右侧三列列宽为150
        for col in right_cols:
            ws.column_dimensions[get_column_letter(col)].width = 150
        # 设置行高
        ws.row_dimensions[target_row].height = 50

    # 保存最终文件
    wb.save(output_path)
    print(f"广告效率表已保存至: {output_path}")
    return ranking_percent


def _ops_gt10_ignore_200(review_interval: dict) -> bool:
    """运营难度是否命中 >10%，仅判断前4段（忽略 200以上）。"""
    if not isinstance(review_interval, dict):
        return False
    ops = review_interval.get('运营难度') or []
    if not isinstance(ops, list):
        return False
    for x in ops[:4]:
        t = str(x).replace('%', '').replace('％', '').strip()
        if not t:
            continue
        try:
            if float(t) > 10:
                return True
        except Exception:
            m = re.search(r'(\d+(?:\.\d+)?)', t)
            if m and float(m.group(1)) > 10:
                return True
    return False


async def _ad_difficulty_for_one_asin(
    asin: str,
    kw_map: dict,
    source_map: dict,
    asin_price_dict: dict,
) -> tuple[str, dict]:
    """单 ASIN 广告难度（供并发调度）。"""
    rp_candidates: list[float] = []
    details: dict = {}
    price_info = asin_price_dict.get(asin) or asin_price_dict.get(str(asin).upper()) or {}
    for keyword, products in (kw_map or {}).items():
        df = pd.DataFrame(products)
        if df.empty:
            details[keyword] = {'matched': False, 'ranking_percent': 0}
            continue
        source_kind = (source_map.get(asin, {}) or {}).get(keyword, 'search')
        if source_kind == 'data_origin':
            clean_data = df
        else:
            clean_data = await save_cleaned_data_orign_to_excel(
                df, keyword, asin, price_info
            )
        review_interval = await save_review_interval_analysis_to_excel(clean_data, keyword, asin)
        matched = _ops_gt10_ignore_200(review_interval)
        if not matched:
            details[keyword] = {'matched': False, 'ranking_percent': 0}
            print(f"ASIN {asin} 关键词 {keyword} 运营难度<=10%(前4段)，跳过广告效率表。")
            continue
        rp = await save_ad_efficiency_table(clean_data, keyword, asin)
        rp_num = pd.to_numeric(rp, errors='coerce')
        if not pd.isna(rp_num) and float(rp_num) >= 0:
            rp_candidates.append(float(rp_num))
            details[keyword] = {'matched': True, 'ranking_percent': float(rp_num)}
        else:
            details[keyword] = {'matched': True, 'ranking_percent': 0}
    payload = {
        'ranking_percent': round(min(rp_candidates), 3) if rp_candidates else 0.0,
        'keywords': details,
    }
    return asin, payload


async def calculate_ad_difficulty_for_asins(target_asins: list[str] | None = None) -> dict:
    """
    从本地 file/{ASIN}/{关键词} 数据重算广告难度：
    - 每个关键词先判断运营难度前4段是否存在 >10%（忽略 200以上）
    - 命中才生成广告效率表并产出该关键词 ranking_percent
    - ASIN 级 ranking_percent 取有效关键词最小值；若都不命中则为 0
    - 多 ASIN 并发（受 ROI_SCHEDULER_ASIN_MAX_CONCURRENT 限制）
    """
    nested_result, _keyword_dict, source_map = await asyncio.to_thread(load_products_from_local_files)
    if target_asins:
        allow = {str(x).strip().upper() for x in target_asins if str(x).strip()}
        nested_result = {a: m for a, m in nested_result.items() if str(a).strip().upper() in allow}
        source_map = {a: m for a, m in source_map.items() if str(a).strip().upper() in allow}
    asin_price_dict = await advertisement_main(target_asins)
    if not nested_result:
        return {}

    max_asin = env_max_concurrent('scheduler_asin', 4)
    sem = asyncio.Semaphore(max_asin)
    out: dict = {}

    async def _run_one(asin: str, kw_map: dict) -> None:
        async with sem:
            try:
                a, payload = await _ad_difficulty_for_one_asin(
                    asin, kw_map, source_map, asin_price_dict
                )
                out[a] = payload
            except Exception as exc:
                print(f"警告: ASIN {asin} 广告难度计算失败: {exc}")
                out[asin] = {'ranking_percent': 0.0, 'keywords': {}, 'error': str(exc)}

    await asyncio.gather(*[_run_one(a, m) for a, m in nested_result.items()])
    return out


def _node_path_from_record(record: dict) -> str:
    """从单行产品字典中取类目路径（兼容映射后字段名与 Excel 原文列名）。"""
    if not record:
        return ""
    for key in (
            "nodeLabelPath",
            "类目路径",
            "节点标签路径",
            "节点路径",
            "nodeLabelPathLocale",
    ):
        val = record.get(key)
        if val is None:
            continue
        if isinstance(val, float) and pd.isna(val):
            continue
        s = str(val).strip()
        if s and s.lower() != "nan":
            return s
    return ""


async def collect_node_label_paths(
        keyword_dict: dict, result: dict, target_asins: list = None
) -> dict:
    """
    从爬取/本地加载结果中为每个目标 ASIN 收集一个 nodeLabelPath。

    result 支持两种结构：
    - 嵌套：{asin: {keyword: products_list}}（本地 file/{ASIN}/{关键词}/ 扫描结果）
    - 扁平：{keyword: products_list}（旧版 fetch_multiple_keywords）
    """
    if target_asins is None:
        target_asins = list(keyword_dict.keys())
    else:
        target_asins = [a for a in target_asins if a in keyword_dict]

    asin_to_path = {}
    if not result:
        return asin_to_path

    first_val = next(iter(result.values()))
    nested = isinstance(first_val, dict) and not isinstance(first_val, list)

    if nested:
        for asin in target_asins:
            kw_map = result.get(asin) or {}
            node_path = ""
            src_kw = ""
            for kw, products in kw_map.items():
                for rec in products or []:
                    node_path = _node_path_from_record(rec)
                    if node_path:
                        src_kw = kw
                        break
                if node_path:
                    break
            if node_path:
                asin_to_path[asin] = node_path
                print(f"为 ASIN {asin} 获取 nodeLabelPath: {node_path} (关键词: {src_kw})")
            else:
                asin_to_path[asin] = ""
                print(
                    f"警告：ASIN {asin} 在 Excel 中未找到有效「类目路径」/nodeLabelPath，"
                    f"ROI 中相关接口将使用空路径。"
                )
        return asin_to_path

    for asin in target_asins:
        node_path = ""
        src_kw = ""
        for ky, products in result.items():
            if ky not in keyword_dict.get(asin, []):
                continue
            for rec in products or []:
                node_path = _node_path_from_record(rec)
                if node_path:
                    src_kw = ky
                    break
            if node_path:
                break
        if node_path:
            asin_to_path[asin] = node_path
            print(f"为 ASIN {asin} 获取 nodeLabelPath: {node_path} (关键词: {src_kw})")
        else:
            asin_to_path[asin] = ""
            print(
                f"警告：ASIN {asin} 未找到有效类目路径，ROI 中相关接口将使用空路径。"
            )
    return asin_to_path


def asin_image_file(asin: str) -> Path:
    """ASIN 主图绝对路径：scripts/asin_find_project/images/<ASIN>.jpg"""
    return IMAGES_DIR / f"{str(asin).strip().upper()}.jpg"


def _parse_unit_purchase_cell(raw) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    t = str(raw).replace('￥', '').replace(',', '').strip()
    if not t or t.upper() in ('N/A', 'NA', '-', '—'):
        return None
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def _positive_float(val) -> float | None:
    """解析为正数；0/空/无效视为缺失。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _parse_money(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        s = str(val).replace('$', '').replace('￥', '').replace(',', '').strip()
        if not s or s.upper() in ('N/A', 'NA', '-', '—'):
            return None
        n = float(s)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_percent(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        s = str(val).replace('%', '').replace(',', '').strip()
        if not s or s.upper() in ('N/A', 'NA', '-', '—'):
            return None
        n = float(s)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def read_labeled_field_from_roi_pack(asin: str, label: str) -> float | None:
    """从 ROI-US-pack 任意列组读取带「字段/值」结构的数值。"""
    a = str(asin).strip().upper()
    pack = FILE_DATA_ROOT / a / f"{a}_ROI-US-pack.xlsx"
    if not pack.is_file():
        return None
    try:
        df = pd.read_excel(pack)
        for _, row in df.iterrows():
            for col_idx in range(len(row)):
                field = str(row.iloc[col_idx]).strip() if pd.notna(row.iloc[col_idx]) else ''
                if field != label:
                    continue
                val_col = col_idx + 1
                if val_col < len(row):
                    cell = row.iloc[val_col]
                    if label == '退款率':
                        parsed = _parse_percent(cell)
                    else:
                        parsed = _parse_money(cell)
                    if parsed is None:
                        parsed = _parse_unit_purchase_cell(cell)
                    if parsed is not None:
                        return parsed
    except Exception as e:
        print(f"读取 ROI 字段「{label}」失败 ({pack}): {e}")
    return None


def read_text_field_from_roi_pack(asin: str, label: str) -> str | None:
    a = str(asin).strip().upper()
    pack = FILE_DATA_ROOT / a / f"{a}_ROI-US-pack.xlsx"
    if not pack.is_file():
        return None
    try:
        df = pd.read_excel(pack)
        for _, row in df.iterrows():
            for col_idx in range(len(row)):
                field = str(row.iloc[col_idx]).strip() if pd.notna(row.iloc[col_idx]) else ''
                if field != label:
                    continue
                val_col = col_idx + 1
                if val_col < len(row) and pd.notna(row.iloc[val_col]):
                    url = str(row.iloc[val_col]).strip()
                    if url and url.upper() not in ('N/A', 'NA', 'NAN'):
                        return url
    except Exception as e:
        print(f"读取 ROI 文本字段「{label}」失败 ({pack}): {e}")
    return None


def build_local_product_hints(nested_result: dict, asin: str) -> dict:
    """从本地 Excel 提取类目路径（供退款率接口入参，不作数值回落）。"""
    hints: dict = {}
    a = str(asin).strip().upper()
    kw_map = nested_result.get(a) or nested_result.get(asin) or {}
    for products in kw_map.values():
        for rec in products or []:
            if not isinstance(rec, dict):
                continue
            if not hints.get('nodeLabelPath'):
                path = _node_path_from_record(rec)
                if path:
                    hints['nodeLabelPath'] = path
                    break
        if hints.get('nodeLabelPath'):
            break
    return hints


def _resolve_image_url_for_roi(
    asin: str,
    info: dict | None,
) -> str:
    url = str((info or {}).get('imageUrl') or '').strip()
    if url and url.upper() not in ('N/A', 'NA', 'NAN'):
        return url
    cached = read_image_url_from_roi_pack(asin)
    if cached and str(cached).strip().upper() not in ('N/A', 'NA', 'NAN', ''):
        return str(cached).strip()
    return f'https://www.amazon.com/dp/{str(asin).strip().upper()}'


async def _resolve_refund_rate(
    asin: str,
    node_label_path: str,
    hints: dict | None,
    refund_cache: dict[str, float] | None = None,
) -> float:
    path = (node_label_path or '').strip() or str((hints or {}).get('nodeLabelPath') or '').strip()
    if not path:
        print(
            f'警告: ASIN {asin} 缺少类目路径，退款率使用默认值 {ROI_DEFAULT_REFUND_RATE}%'
        )
        return ROI_DEFAULT_REFUND_RATE
    if refund_cache is not None and path in refund_cache:
        return refund_cache[path]
    try:
        refund_raw = await fetch_refund_rate_for_path(path)
        text = str(refund_raw or '').replace('%', '').strip()
        if not text:
            raise ValueError('退款率接口无数据')
        val = float(text)
        if val <= 0:
            raise ValueError(f'退款率无效: {val}')
    except Exception as exc:
        print(
            f'警告: ASIN {asin} 退款率获取失败（{exc}），'
            f'使用默认值 {ROI_DEFAULT_REFUND_RATE}%'
        )
        return ROI_DEFAULT_REFUND_RATE
    if refund_cache is not None:
        refund_cache[path] = val
    return val


async def prefetch_refund_rates(
    paths: list[str],
    *,
    max_concurrent: int | None = None,
) -> dict[str, float]:
    """按类目路径批量预取退款率（同一路径只请求一次；失败类目不中断整批）。"""
    limit = max_concurrent or env_max_concurrent('sellersprite', 6)
    out, failures = await prefetch_refund_rates_batch(paths, max_concurrent=limit)
    if failures:
        emit_progress(
            f'退款率：{len(out)} 个类目成功，{len(failures)} 个类目无数据（相关 ASIN 将单独失败）'
        )
        for row in failures[:8]:
            emit_progress(f"  退款率跳过: {str(row.get('path', ''))[:55]}…")
        if len(failures) > 8:
            emit_progress(f'  … 另有 {len(failures) - 8} 个类目无退款率')
    return out


async def _resolve_fba_and_head(
    asin: str,
    fba_info_dict: dict,
    head_distance_override: float | None,
) -> tuple[float, float]:
    info = fba_info_dict.get(asin) or {}
    if not isinstance(info, dict):
        info = {}

    fba_fee = _parse_money(info.get('FBA'))
    head_distance = info.get('head_distance')
    if head_distance is not None:
        try:
            head_distance = float(head_distance)
        except (TypeError, ValueError):
            head_distance = None

    if fba_fee is None or fba_fee <= 0:
        print(
            f'警告: ASIN {asin} 无法获取 FBA 配送费，'
            f'使用默认值 ${ROI_DEFAULT_FBA_FEE}'
        )
        fba_fee = ROI_DEFAULT_FBA_FEE

    if head_distance_override is not None:
        head_distance = head_distance_override
    elif head_distance is None:
        head_distance = 0.0

    return float(fba_fee), float(head_distance)


def read_unit_purchase_from_roi_pack(asin: str) -> float | None:
    """从已有 ROI-US-pack 表读取「单件采购」，供图搜失败时回落。"""
    return read_labeled_field_from_roi_pack(asin, '单件采购')


def read_image_url_from_roi_pack(asin: str) -> str | None:
    """从已有 ROI-US-pack 读取「图片链接」。"""
    return read_text_field_from_roi_pack(asin, '图片链接')


async def ensure_asin_image_path(
    asin: str,
    info: dict | None,
    current_path: str = "",
) -> str | None:
    """确保 ASIN 主图存在；仅使用卖家精灵广告接口返回的 imageUrl。"""
    p = Path(current_path) if current_path else asin_image_file(asin)
    if p.is_file():
        return str(p.resolve())

    url = str((info or {}).get('imageUrl') or '').strip()
    if not url or url.upper() in ('N/A', 'NA', 'NAN'):
        return None

    got = await download_one(asin, {'imageUrl': url})
    if got:
        return got
    return None


async def _fetch_unit_purchase_via_taobao(image_file: str, tokens: list[str]) -> float | None:
    """1688 以图搜价；失败时用 prefer_network 刷新 token 再试一次。"""
    if not tokens or len(tokens) < 2:
        print('淘宝 token 不可用，跳过图搜')
        return None
    val = await async_price_info_main(image_file, tokens[0], tokens[1])
    if val is not None:
        return val
    print('图搜无结果或 token 失效，尝试刷新淘宝 token 后重试…')
    fresh = await asyncio.to_thread(lambda: get_taobao_tokens(prefer_network=True))
    return await async_price_info_main(image_file, fresh['_m_h5_tk'], fresh['_m_h5_tk_enc'])


async def save_roi_us_pack(nodeLabelPath: str,
                           fba_info_dict: dict,
                           asin: str,
                           asin_cpc_list: list,
                           monthly_sales_dict: dict,
                           tokens: list[str],
                           image_path: str,
                           exchange_rate: float = 7.2,
                           asin_info_dict: dict = None,
                           unit_purchase_override: float | None = None,
                           head_distance_override: float | None = None,
                           local_hints: dict | None = None,
                           refund_cache: dict[str, float] | None = None):
    """
    生成 ROI-US-pack 表，输出三组并排数据：左侧基础成本、中间广告相关、右侧流量与利润指标，
    每组包含字段、值、单位三列。
    """
    product_asin = asin
    hints = local_hints or {}
    node_label_path = (nodeLabelPath or '').strip() or str(hints.get('nodeLabelPath') or '').strip()

    # ==================== 1. 获取基础数据 ====================
    fba_fee, head_distance = await _resolve_fba_and_head(
        product_asin,
        fba_info_dict,
        head_distance_override,
    )

    if unit_purchase_override is not None:
        unit_purchase = unit_purchase_override
    else:
        resolved_image = await ensure_asin_image_path(
            product_asin, asin_info_dict or {}, image_path or ''
        )
        if resolved_image:
            unit_purchase = await _fetch_unit_purchase_via_taobao(resolved_image, tokens)
            print(unit_purchase, asin, '3333')
        else:
            unit_purchase = None
            print(f'警告: ASIN {asin} 主图不可用，跳过图搜')
        if unit_purchase is None:
            unit_purchase = read_unit_purchase_from_roi_pack(product_asin)
        if unit_purchase is None:
            unit_purchase = ROI_DEFAULT_UNIT_PURCHASE
            print(
                f'警告: ASIN {asin} 无法获取单件采购价，'
                f'使用默认值 ￥{ROI_DEFAULT_UNIT_PURCHASE}'
            )

    platform_commission = 15

    refund_rate = await _resolve_refund_rate(
        product_asin, node_label_path, hints, refund_cache=refund_cache
    )

    asin_price = _positive_float((asin_info_dict or {}).get('avg_price'))

    # 计算基础售价
    if unit_purchase is not None and head_distance is not None:
        cost_cny = unit_purchase + head_distance
        cost_usd = cost_cny / exchange_rate
        total_cost = cost_usd + fba_fee
        denominator = 1 - (platform_commission + refund_rate) / 100
        if denominator <= 0:
            print(f'警告: ASIN {asin} 佣金+退款率过高，退款率改用默认值')
            refund_rate = ROI_DEFAULT_REFUND_RATE
            denominator = 1 - (platform_commission + refund_rate) / 100
        lowest_price = total_cost / denominator if denominator > 0 else None
    else:
        lowest_price = None

    if asin_price is not None:
        product_price = asin_price * 1.02
    elif lowest_price is not None:
        product_price = lowest_price * 2
    else:
        product_price = ROI_DEFAULT_PRODUCT_PRICE
        print(
            f'警告: ASIN {asin} 无法推算售价，'
            f'使用默认值 ${ROI_DEFAULT_PRODUCT_PRICE}'
        )

    discount = 0
    if product_price is not None:
        discounted_price = product_price * (1 - discount / 100)
        refund_amount = product_price * (refund_rate / 100)
        commission_amount = discounted_price * (platform_commission / 100)
        shipping_fba = fba_fee

        sales_return = discounted_price - refund_amount - commission_amount - shipping_fba
        if unit_purchase is not None and head_distance is not None:
            cost_cny = unit_purchase + head_distance
            cost_usd = cost_cny / exchange_rate
            actual_profit = sales_return - cost_usd
            actual_cost = discounted_price - actual_profit
        else:
            actual_profit = None
            actual_cost = None
    else:
        discounted_price = None
        sales_return = None
        actual_profit = None
        actual_cost = None

    if actual_profit is None or discounted_price is None or discounted_price <= 0:
        if product_price is None:
            product_price = ROI_DEFAULT_PRODUCT_PRICE
        discounted_price = product_price * (1 - discount / 100)
        if unit_purchase is None:
            unit_purchase = ROI_DEFAULT_UNIT_PURCHASE
        if head_distance is None:
            head_distance = 0.0
        if fba_fee is None or fba_fee <= 0:
            fba_fee = ROI_DEFAULT_FBA_FEE
        cost_usd = (float(unit_purchase) + float(head_distance)) / exchange_rate
        commission_amount = discounted_price * (platform_commission / 100)
        refund_amount = product_price * (refund_rate / 100)
        sales_return = discounted_price - refund_amount - commission_amount - fba_fee
        actual_profit = max(sales_return - cost_usd, 0.01)
        actual_cost = discounted_price - actual_profit
        print(
            f'警告: ASIN {asin} 利润数据不完整，已用默认值估算 '
            f'（折后价={discounted_price:.2f}，利润={actual_profit:.2f}）'
        )

    product_key = str(product_asin).strip().upper()
    monthly_sales = (
        monthly_sales_dict.get(product_asin)
        or monthly_sales_dict.get(product_key)
        or 0.0
    )
    if not monthly_sales:
        monthly_sales = 0.0
    daily_orders = monthly_sales / 30.0 if monthly_sales > 0 else 0.0

    # ==================== 2. 广告相关计算 ====================
    ad_cpc, conversion_rate, ad_clicks = resolve_sif_ad_metrics(
        product_asin,
        asin_cpc_list,
        daily_orders,
    )

    ad_budget = ad_cpc * ad_clicks

    # 日利润、月利润（出单量为 0 时按 0 计，仍保留单位经济学指标）
    daily_profit1 = actual_profit * daily_orders - ad_budget
    daily_profit2 = daily_profit1 * exchange_rate
    monthly_profit1 = daily_profit1 * 30
    monthly_profit2 = daily_profit2 * 30

    # 广告费占比（出单量为 0 时广告占比为 0，去广告毛利率 = 利润率）
    if discounted_price > 0:
        if daily_orders > 0:
            ad_cost_ratio = ad_budget / (discounted_price * daily_orders) * 100
        else:
            ad_cost_ratio = 0.0
    else:
        ad_cost_ratio = 0.0

    # ==================== 3. 右侧新增字段计算 ====================
    cost_cny_total = (
            unit_purchase + head_distance) if unit_purchase is not None and head_distance is not None else None

    # 总流量
    if conversion_rate is not None and conversion_rate > 0 and daily_orders is not None:
        total_traffic = daily_orders / conversion_rate
    else:
        total_traffic = None

    # 日自然流量
    if total_traffic is not None:
        daily_natural_traffic = total_traffic * 0.5
    else:
        daily_natural_traffic = None

    # 每单需点击
    if conversion_rate is not None and conversion_rate > 0:
        clicks_per_order = 1 / conversion_rate
    else:
        clicks_per_order = None

    # 去广告投产
    if cost_cny_total is not None and cost_cny_total > 0 and daily_orders > 0:
        profit_cny = daily_profit1 * exchange_rate
        ad_removed_roi = profit_cny / (cost_cny_total * daily_orders)
    elif cost_cny_total is not None and cost_cny_total > 0:
        ad_removed_roi = 0.0
    else:
        ad_removed_roi = None

    # 每单利润
    if daily_orders > 0:
        profit_per_order = daily_profit2 / daily_orders
    else:
        profit_per_order = 0.0

    # 投产比
    if cost_cny_total is not None and cost_cny_total > 0:
        roi_ratio = (actual_profit * exchange_rate) / cost_cny_total * 100
    else:
        roi_ratio = None

    # 利润率 / 去广告毛利率（正常流程必须产出数值）
    profit_margin = (actual_profit / discounted_price) * 100
    ad_removed_gross_margin = profit_margin - (ad_cost_ratio or 0.0)
    # 单件采购+单件头程
    unit_head_price = (
        unit_purchase + head_distance
        if unit_purchase is not None and head_distance is not None
        else None
    )
    target_asin_url = f'https://www.amazon.com/DP/{asin}'
    link1688 = 'https://aibuy.1688.com/landingpage/home/inventory/products.html?bizType=selectionTool&customerId=sellerspriteLP&lang=zh&currency=CNY'
    imageUrl = _resolve_image_url_for_roi(product_asin, asin_info_dict)

    # ==================== 4. 构建三组带单位的 DataFrame ====================
    # 左侧：基础成本与售价
    left_fields = [
        '单件采购', '单件头程', '平台佣金', '退款率', 'FBA配送',
        '最低售价', '产品售价', '优惠折扣', '折后价格', '平台佣金',
        '实际利润', '销售回款', '实际成本', '投产比'
    ]
    left_values = [
        f"{unit_purchase:.2f}" if unit_purchase is not None else 'N/A',
        f"{head_distance:.2f}" if head_distance is not None else 'N/A',
        f"{platform_commission}",
        f"{refund_rate:.2f}",
        f"{fba_fee:.2f}",
        f"{lowest_price:.2f}" if lowest_price is not None else 'N/A',
        f"{product_price:.2f}" if product_price is not None else 'N/A',
        f"{discount}",
        f"{discounted_price:.2f}" if discounted_price is not None else 'N/A',
        f"{platform_commission}",
        f"{actual_profit:.2f}" if actual_profit is not None else 'N/A',
        f"{sales_return:.2f}" if sales_return is not None else 'N/A',
        f"{actual_cost:.2f}" if actual_cost is not None else 'N/A',
        f"{roi_ratio:.2f}" if roi_ratio is not None else 'N/A'
    ]
    left_units = [
        '￥', '￥', '%', '%', '$',
        '$', '$', '%', '$', '%',
        '$', '$', '$', '%'
    ]

    # 中间：广告相关
    middle_fields = [
        '广告预算', '广告cpc', '广告点击', '转化率', '月出单量', '出单量',
        '日利润1', '日利润2', '月利润1', '月利润2', '广告费占比','图片链接',
        'asin链接','1688链接'
    ]
    middle_values = [
        f"{ad_budget:.2f}",
        f"{ad_cpc:.2f}",
        f"{ad_clicks:.2f}",
        f"{conversion_rate * 100:.2f}",
        f"{daily_orders * 30:.2f}" if daily_orders else 'N/A',
        f"{daily_orders:.2f}" if daily_orders else 'N/A',
        f"{daily_profit1:.2f}" if daily_profit1 is not None else 'N/A',
        f"{daily_profit2:.2f}" if daily_profit2 is not None else 'N/A',
        f"{monthly_profit1:.2f}" if monthly_profit1 is not None else 'N/A',
        f"{monthly_profit2:.2f}" if monthly_profit2 is not None else 'N/A',
        f"{ad_cost_ratio:.2f}" if ad_cost_ratio is not None else 'N/A',
        imageUrl,
        f"{target_asin_url}" if target_asin_url is not None else 'N/A',
        f"{link1688}" if link1688 is not None else 'N/A'
    ]
    middle_units = [
        '$', '$', '次', '%', '单', '单',
        '$', '￥', '$', '￥', '%','a',
        'a','a'
    ]

    # 右侧：流量与利润指标
    extra_fields = [
        '总流量', '日自然流量', '每单需点击', '去广告投产',
        '每单利润', '采购总价格', '利润率', '去广告毛利率'
    ]
    extra_values = [
        f"{total_traffic:.2f}" if total_traffic is not None else 'N/A',
        f"{daily_natural_traffic:.2f}" if daily_natural_traffic is not None else 'N/A',
        f"{clicks_per_order:.2f}" if clicks_per_order is not None else 'N/A',
        f"{ad_removed_roi * 100:.2f}" if ad_removed_roi is not None else 'N/A',
        f"{profit_per_order:.2f}" if profit_per_order is not None else 'N/A',
        f"{unit_head_price:.2f}" if unit_head_price is not None else 'N/A',
        f"{profit_margin:.2f}",
        f"{ad_removed_gross_margin:.2f}"
    ]
    extra_units = [
        '次', '次', '次', '%',
        '￥', '￥', '%', '%'
    ]

    # 构建三个 DataFrame
    left_df = pd.DataFrame({'字段': left_fields, '值': left_values, '单位': left_units})
    middle_df = pd.DataFrame({'字段': middle_fields, '值': middle_values, '单位': middle_units})
    extra_df = pd.DataFrame({'字段': extra_fields, '值': extra_values, '单位': extra_units})

    # 水平合并
    result_df = pd.concat([left_df, middle_df, extra_df], axis=1)

    # 保存 Excel（先写临时文件，成功后再替换，避免失败时覆盖旧 ROI-US-pack）
    output_dir = await verify_path(asin=asin)
    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f'{product_asin}_ROI-US-pack.xlsx'
    tmp_path = output_path.with_suffix('.part.xlsx')
    if tmp_path.is_file():
        tmp_path.unlink(missing_ok=True)
    try:
        result_df.to_excel(tmp_path, index=False)

        # ==================== 样式设置（含移动右侧特殊字段） ====================
        wb = load_workbook(tmp_path)
        ws = wb.active

        # 特殊字段名称
        special_field_names = ['去广告投产', '采购总价格', '每单利润', '利润率', '去广告毛利率']

        # 右侧三列的列号（假设三组列分别为 1-3, 4-6, 7-9）
        right_cols = [7, 8, 9]  # 字段列、值列、单位列

        # 找到右侧字段列中所有特殊字段的行
        special_rows = []
        for row in range(2, ws.max_row + 1):
            field_cell = ws.cell(row=row, column=right_cols[0])
            if field_cell.value in special_field_names:
                special_rows.append(row)

        if special_rows:
            # 收集这些行的右侧三列数据
            special_data = []
            for row in special_rows:
                row_data = []
                for col in right_cols:
                    row_data.append(ws.cell(row=row, column=col).value)
                special_data.append(row_data)

            # 在原位置清空这些单元格
            for row in special_rows:
                for col in right_cols:
                    ws.cell(row=row, column=col).value = ''

            # 找到表格末尾行（最后一行的下一行）
            last_row = ws.max_row
            # 将特殊数据追加到底部
            for i, row_data in enumerate(special_data):
                new_row = last_row + 1 + i
                for j, col in enumerate(right_cols):
                    ws.cell(row=new_row, column=col).value = row_data[j]

            # 为移动后的特殊行设置样式（行高、字体）
            for i, row_data in enumerate(special_data):
                new_row = last_row + 1 + i
                ws.row_dimensions[new_row].height = 50
                for col in right_cols:
                    cell = ws.cell(row=new_row, column=col)
                    cell.font = Font(size=36, bold=True)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

        # 1. 设置列宽
        for col in range(1, ws.max_column + 1):
            col_letter = get_column_letter(col)
            cell_value = ws.cell(row=1, column=col).value
            if cell_value == '单位':
                ws.column_dimensions[col_letter].width = 10
            else:
                ws.column_dimensions[col_letter].width = 25

        # 右侧值列（第8列）宽45
        right_value_col = 8
        ws.column_dimensions[get_column_letter(right_value_col)].width = 45
        ws.column_dimensions[get_column_letter(7)].width = 45

        # 2. 设置行高（所有行先30）
        for row in range(1, ws.max_row + 1):
            ws.row_dimensions[row].height = 30

        # 3. 设置全局字体（所有单元格18加粗，居中）
        bold_font = Font(size=18, bold=True)
        for row in ws.iter_rows():
            for cell in row:
                cell.font = bold_font
                cell.alignment = Alignment(horizontal='center', vertical='center')

        # 4. 重新为移动后的特殊行设置样式（避免被全局覆盖）
        if special_rows:
            for i, row_data in enumerate(special_data):
                new_row = last_row + 1 + i
                ws.row_dimensions[new_row].height = 50
                for col in right_cols:
                    cell = ws.cell(row=new_row, column=col)
                    cell.font = Font(size=36, bold=True)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

        # 5. 高亮指定字段
        yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        highlight_fields = [
            '最低售价', '折后价格', '平台佣金', '实际利润', '销售回款', '实际成本',
            '广告预算', '广告点击', '出单量', '日利润1', '日利润2', '月利润1', '月利润2',
            '广告费占比', '总流量', '日自然流量', '每单需点击', '去广告投产', '每单利润',
            '投产比', '利润率', '去广告毛利率', '采购总价格'
        ]

        # 找到所有“值”列
        value_cols = []
        for col in range(1, ws.max_column + 1):
            if ws.cell(row=1, column=col).value == '值':
                value_cols.append(col)

        for row in range(2, ws.max_row + 1):
            for val_col in value_cols:
                field_col = val_col - 1
                field_cell = ws.cell(row=row, column=field_col)
                if field_cell.value in highlight_fields:
                    value_cell = ws.cell(row=row, column=val_col)
                    value_cell.fill = yellow_fill

        # 保存最终样式
        wb.save(tmp_path)
        shutil.move(str(tmp_path), str(output_path))
    except Exception as exc:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
        print(f'警告: ASIN {product_asin} 样式写入失败（{exc}），改为保存简化版 ROI-US-pack')
        result_df.to_excel(output_path, index=False)
        emit_progress(f'ASIN {product_asin} ROI-US-pack 已生成（简化版）')

    print(f"ROI-US-pack 表已保存至: {output_path}")
    if not output_path.is_file():
        raise RuntimeError(f'ASIN {product_asin} ROI-US-pack 写入失败')
    emit_progress(f'ASIN {product_asin} ROI-US-pack 已生成')
    return {
        product_asin: {
            # 看板「去广告毛利率」列对应 profit_margin 字段
            'profit_margin': round(ad_removed_gross_margin, 2),
            'gross_profit_rate': round(profit_margin, 2),
            'unit_purchase': unit_purchase,
            'monthly_profit1': monthly_profit1,
            'monthly_results': monthly_sales,
            'profit_per_order': profit_per_order,
            'head_distance': head_distance,
            'actual_cost': actual_cost,
            'ad_removed_roi': ad_removed_roi,
        }
    }


async def force_write_minimal_roi_us_pack(
    asin: str,
    exchange_rate: float = 7.2,
) -> dict:
    """极端兜底：用默认值写出 ROI-US-pack（确保计算 ROI 页能识别为已计算）。"""
    product_asin = str(asin).strip().upper()
    unit_purchase = ROI_DEFAULT_UNIT_PURCHASE
    head_distance = 0.0
    fba_fee = ROI_DEFAULT_FBA_FEE
    refund_rate = ROI_DEFAULT_REFUND_RATE
    product_price = ROI_DEFAULT_PRODUCT_PRICE
    discounted_price = product_price
    actual_profit = max(discounted_price * 0.15, 0.01)
    ad_cpc = SIF_DEFAULT_AD_CPC
    conversion_rate = SIF_DEFAULT_CONVERSION_RATE
    ad_clicks = SIF_DEFAULT_AD_CLICKS
    ad_budget = ad_cpc * ad_clicks
    profit_margin = (actual_profit / discounted_price) * 100
    ad_removed_gross_margin = profit_margin

    left_fields = ['单件采购', '单件头程', '平台佣金', '退款率', 'FBA配送', '折后价格', '实际利润']
    left_values = [
        f'{unit_purchase:.2f}', f'{head_distance:.2f}', '15', f'{refund_rate:.2f}',
        f'{fba_fee:.2f}', f'{discounted_price:.2f}', f'{actual_profit:.2f}',
    ]
    left_units = ['￥', '￥', '%', '%', '$', '$', '$']
    middle_fields = ['广告预算', '广告cpc', '广告点击', '转化率', '图片链接', 'asin链接']
    middle_values = [
        f'{ad_budget:.2f}', f'{ad_cpc:.2f}', f'{ad_clicks:.2f}',
        f'{conversion_rate * 100:.2f}',
        f'https://www.amazon.com/dp/{product_asin}',
        f'https://www.amazon.com/dp/{product_asin}',
    ]
    middle_units = ['$', '$', '次', '%', 'a', 'a']
    extra_fields = ['利润率', '去广告毛利率']
    extra_values = [f'{profit_margin:.2f}', f'{ad_removed_gross_margin:.2f}']
    extra_units = ['%', '%']

    left_df = pd.DataFrame({'字段': left_fields, '值': left_values, '单位': left_units})
    middle_df = pd.DataFrame({'字段': middle_fields, '值': middle_values, '单位': middle_units})
    extra_df = pd.DataFrame({'字段': extra_fields, '值': extra_values, '单位': extra_units})
    result_df = pd.concat([left_df, middle_df, extra_df], axis=1)

    output_dir = await verify_path(asin=product_asin)
    os.makedirs(output_dir, exist_ok=True)
    output_path = Path(output_dir) / f'{product_asin}_ROI-US-pack.xlsx'
    result_df.to_excel(output_path, index=False)
    emit_progress(f'ASIN {product_asin} 已用默认值强制生成 ROI-US-pack')
    print(f'强制生成 ROI-US-pack: {output_path}')
    return {
        product_asin: {
            'profit_margin': round(ad_removed_gross_margin, 2),
            'gross_profit_rate': round(profit_margin, 2),
            'unit_purchase': unit_purchase,
            'monthly_profit1': 0.0,
            'monthly_results': 0.0,
            'profit_per_order': 0.0,
            'head_distance': head_distance,
            'actual_cost': discounted_price - actual_profit,
            'ad_removed_roi': 0.0,
        }
    }


async def get_month_number(asin_list: list, data_nested: dict, key_list: dict):
    """
    按 ASIN 汇总目标月销（来自各关键词），再对关键词取平均。

    data_nested: {asin: {keyword: 目标月销数值}}
    key_list: {asin: [keyword, ...]}，须与扫描/业务关键词列表一致
    """
    asin_month = {}
    for a in asin_list:
        kws = key_list.get(a) or []
        if not kws:
            asin_month[a] = 0.0
            continue
        inner = data_nested.get(a) or {}
        total = sum(inner.get(kw, 0) for kw in kws)
        asin_month[a] = total / len(kws)
    return asin_month


# 并发下载图片到本地（绝对路径：scripts/asin_find_project/images/<ASIN>.jpg）
async def download_one(asin, info):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    local_path = asin_image_file(asin)
    if local_path.is_file():
        print(f"图片已存在: {local_path}")
        return str(local_path)

    image_url = info.get('imageUrl')
    if not image_url:
        print(f"警告: ASIN {asin} 无图片 URL，无法下载主图到 {local_path}")
        return None

    try:
        async with aiohttp.ClientSession(
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': 'https://www.amazon.com/',
            }
        ) as session:
            timeout = aiohttp.ClientTimeout(total=90)
            async with session.get(image_url, timeout=timeout) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) < 256:
                        print(f"下载 {asin} 主图过小({len(content)} bytes)，可能不是有效图片")
                        return None
                    local_path.write_bytes(content)
                    print(f"图片已下载: {local_path} ({len(content)} bytes)")
                    return str(local_path)
                else:
                    print(f"下载失败 {asin}: HTTP {resp.status} url={image_url[:120]}")
    except Exception as e:
        print(f"下载异常 {asin}: {e}")
    return None


async def async_return_info(asin_dict: dict, info_list: list):
    """
    将 monthly_results（按关键词）聚合为按 ASIN 的结构：
    {
      ASIN: {
        "monthly_results": 该 ASIN 下关键词目标月销最大值,
        "review_interval": {
          ASIN: {
            keyword: {"review_interval": <该关键词区间分析字典>}
          }
        },
        "ranking_percent": 该 ASIN 下关键词 ranking_percent 的最小值（越小越优）
      }
    }
    """
    result_dict: Dict[str, Dict[str, Any]] = {}
    try:
        for asin, kw_list in asin_dict.items():
            result_dict[asin] = {
                "monthly_results": 0.0,
                "review_interval": {asin: {}},
                "ranking_percent": 0.0,
            }
            max_monthly = -1.0
            rp_candidates: List[float] = []

            for item in info_list:
                if not item:
                    continue
                try:
                    item_asin = item.get("asin")
                    if item_asin and item_asin != asin:
                        continue

                    monthly_map = item.get("monthly_results", {})
                    if not monthly_map:
                        continue
                    kw = list(monthly_map.keys())[0]
                    if kw not in kw_list:
                        continue

                    month_val = pd.to_numeric(monthly_map.get(kw), errors="coerce")
                    if not pd.isna(month_val) and float(month_val) > max_monthly:
                        max_monthly = float(month_val)

                    review_payload = item.get("review_interval", {})
                    result_dict[asin]["review_interval"][asin][kw] = {
                        "review_interval": review_payload
                    }

                    rp_payload = item.get("ranking_percent", -1)
                    rp_num = pd.to_numeric(rp_payload, errors="coerce")
                    if not pd.isna(rp_num) and rp_num >= 0:  # 允许 0 作为默认值
                        rp_candidates.append(float(rp_num))
                except Exception as e:
                    print(f"<UNK> {asin_dict}: {e}")

            if max_monthly >= 0:
                result_dict[asin]["monthly_results"] = max_monthly
            if rp_candidates:
                result_dict[asin]["ranking_percent"] = round(min(rp_candidates), 3)
    except Exception as e:
        print(f"<不好。数据出问题了1> {asin_dict}: {e}")
    return result_dict


async def async_merging_data(info_list: list, info_dict: dict):
    """
    合并 ROI 结果到 info_dict（按 ASIN 键合并）。
    保留 async_return_info 生成的 ranking_percent 嵌套结构，不做重写。
    """
    try:
        for info in info_list:
            if not info:
                continue
            asin_key = list(info.keys())[0]
            converted_info = {
                k: round(float(v), 2) if isinstance(v, np.float64) else v
                for k, v in info[asin_key].items()
            }
            if asin_key not in info_dict:
                info_dict[asin_key] = {}
            info_dict[asin_key].update(converted_info)

        for key in info_dict:
            info_dict[key] = {
                k: round(float(v), 2) if isinstance(v, np.float64) else v
                for k, v in info_dict[key].items()
            }
    except Exception as e:
        print(f"<不好，数据出问题了3> {info_dict}: {e}")
    return info_dict


ASIN_FOLDER_PATTERN = re.compile(r"^B[A-Z0-9]{9}$")


def normalize_excel_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """列名去空格、按 COLUMN_MAPPING 重命名；多列映射到同一 API 名时保留首列。"""
    out = df.copy()
    out.columns = pd.Index([str(c).strip() for c in out.columns])
    rename_map = {
        k: v for k, v in COLUMN_MAPPING_EXCEL_TO_API.items() if k in out.columns
    }
    out = out.rename(columns=rename_map)
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated(keep="first")]
    return out


def load_products_from_local_files(base_dir: Optional[Path] = None) -> tuple:
    """
    自动扫描本地目录：file/{ASIN}/{关键词文件夹}/Search(*)-*-US-*.xlsx
    不依赖外部传入的关键词列表；ASIN 与关键词均来自文件夹名。

    :param base_dir: 数据根目录，默认 FILE_DATA_ROOT（即 ./file）
    :return: (nested_result, keyword_dict, source_map)
        nested_result: {asin: {keyword_folder_name: [product_dict, ...]}}
        keyword_dict: {asin: [keyword_folder_name, ...]}，供后续加权月销等逻辑使用
        source_map: {asin: {keyword_folder_name: 'data_origin'|'search'|'xlsx'}}
    """
    root = Path(base_dir) if base_dir is not None else FILE_DATA_ROOT
    nested: Dict[str, Dict[str, list]] = {}
    keyword_dict: Dict[str, list] = {}

    source_map: Dict[str, Dict[str, str]] = {}
    if not root.exists():
        print(f"警告：数据根目录不存在: {root.resolve()}")
        return nested, keyword_dict, source_map

    for asin_dir in sorted(root.iterdir()):
        if not asin_dir.is_dir():
            continue
        asin = asin_dir.name.upper()
        if not ASIN_FOLDER_PATTERN.match(asin):
            continue

        nested[asin] = {}
        keyword_dict[asin] = []
        source_map[asin] = {}
        has_roi_sheet = any(
            p.is_file()
            and p.suffix.lower() == ".xlsx"
            and ("roi-us" in p.name.lower() or "roi_us" in p.name.lower())
            for p in asin_dir.glob("*.xlsx")
        )

        for kw_dir in sorted(asin_dir.iterdir()):
            if not kw_dir.is_dir():
                continue
            kw_name = kw_dir.name

            source_kind = "search"
            if has_roi_sheet:
                excel_files = sorted(kw_dir.glob("*_data_origin.xlsx"))
                if excel_files:
                    source_kind = "data_origin"
                else:
                    excel_files = sorted(kw_dir.glob("Search(*)-*-US-*.xlsx"))
                    source_kind = "search"
            else:
                excel_files = sorted(kw_dir.glob("Search(*)-*-US-*.xlsx"))
            if not excel_files:
                excel_files = sorted(kw_dir.glob("*.xlsx"))
                source_kind = "xlsx"
            if not excel_files:
                print(f"警告：{kw_dir} 中未找到 xlsx")
                continue

            excel_path = excel_files[0]
            print(f"正在读取文件：{excel_path}")
            try:
                df = pd.read_excel(excel_path)
                df = normalize_excel_dataframe(df)
                for col in ["price", "totalUnits", "reviews"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                products = df.to_dict(orient="records")
                nested[asin][kw_name] = products
                keyword_dict[asin].append(kw_name)
                source_map[asin][kw_name] = source_kind
            except Exception as e:
                print(f"读取 Excel 失败 {excel_path}: {e}")

    return nested, keyword_dict, source_map


async def seller_wizard_main(
        parity: float,
        asins: list[str] | None = None,
        cost_overrides: dict | None = None,
):
    FILE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"本地 Excel 根目录: {FILE_DATA_ROOT.resolve()}")
    try:
        taobao_config = await asyncio.to_thread(get_taobao_tokens)
        tokens = [taobao_config["_m_h5_tk"], taobao_config["_m_h5_tk_enc"]]
    except Exception as e:
        print(f"警告: 获取淘宝 token 失败，图搜将尝试回落已有采购价: {e}")
        tokens = []

    # 1. 从 file/{ASIN}/{关键词}/ 自动扫描 Excel（关键词列表由目录结构决定）
    nested_result, keyword_dict, source_map = await asyncio.to_thread(load_products_from_local_files)
    if asins:
        allow = {str(x).strip().upper() for x in asins if str(x).strip()}
        nested_result = {a: m for a, m in nested_result.items() if a.upper() in allow}
        keyword_dict = {a: kws for a, kws in keyword_dict.items() if a.upper() in allow}
        source_map = {a: m for a, m in source_map.items() if a.upper() in allow}
    target_asins = [str(a).strip().upper() for a in nested_result.keys()]
    emit_progress(f'已扫描本地数据：共 {len(target_asins)} 个 ASIN')
    print("从本地扫描得到的 keyword_dict:", keyword_dict)
    if not target_asins:
        emit_progress(f'未在 {FILE_DATA_ROOT} 下发现 ASIN 数据')
        print(f"未在 {FILE_DATA_ROOT} 下发现符合 B0XXXXXXXXX 结构的 ASIN 数据，结束。")
        return {}

    from seller_account_guard import ensure_seller_login

    emit_progress('正在登录卖家精灵并批量拉取 FBA / 广告数据…')
    await ensure_seller_login()
    max_ss = env_max_concurrent('sellersprite', 6)

    try:
        async with async_api_slot('sellersprite'):
            fba_info_dict, asin_info_dict = await asyncio.gather(
                async_fba_batch(target_asins, max_concurrent=max_ss),
                advertisement_main(target_asins, max_concurrent=max_ss),
            )
    except Exception as e:
        if is_seller_account_banned_error(e):
            raise
        raise RuntimeError(f'卖家精灵 FBA/广告批量获取失败: {e}') from e
    print(fba_info_dict, '666666')
    if not isinstance(asin_info_dict, dict):
        asin_info_dict = {}
    asin_info_dict = {
        str(k).strip().upper(): v
        for k, v in asin_info_dict.items()
        if isinstance(v, dict)
    }
    if isinstance(fba_info_dict, dict):
        fba_info_dict = {
            str(k).strip().upper(): v
            for k, v in fba_info_dict.items()
        }
    emit_progress(
        f'卖家精灵数据就绪：FBA {len(fba_info_dict)}/{len(target_asins)}，'
        f'广告 {len(asin_info_dict)}/{len(target_asins)}'
    )

    download_tasks = [download_one(asin, info) for asin, info in asin_info_dict.items()]
    local_paths = await asyncio.gather(*download_tasks)
    # 顺序须与 download_tasks（asin_info_dict.items）一致，勿与 target_asins 盲 zip
    asin_to_image_path = {
        asin: path
        for (asin, _), path in zip(asin_info_dict.items(), local_paths)
        if path
    }

    # 2. SIF：CPC 等（关键词以本地扫描为准）
    try:
        async with async_api_slot('sif'):
            asin_cpc, _ = await async_sif_api.sif_main(target_asins)
    except Exception as e:
        print(f"警告: SIF CPC 获取失败，广告 CPC 将使用默认值: {e}")
        asin_cpc = []
    if not isinstance(asin_cpc, list):
        asin_cpc = []

    asin_path_dict = await collect_node_label_paths(keyword_dict, nested_result, target_asins)

    emit_progress('正在批量获取退款率…')
    refund_cache = await prefetch_refund_rates(
        list(asin_path_dict.values()),
        max_concurrent=max_ss,
    )
    emit_progress(f'退款率预取完成：{len(refund_cache)} 个类目')

    roi_failures: list[dict[str, str]] = []

    # ========== 3. 并发处理每个 (ASIN, 关键词) ==========
    async def process_one_keyword(asin: str, keyword: str, products: list):
        """清洗 -> 市场容量 -> 评论区间 -> 广告效率表，输出写入 file/{asin}/"""
        try:
            print(f"\n处理 ASIN={asin} 关键词: {keyword}")
            print(f"清洗前的数据行数：{len(products)}")
            df = pd.DataFrame(products)
            ranking_percent = 0
            if df.empty:
                return None
            source_kind = (source_map.get(asin, {}) or {}).get(keyword, "search")
            if source_kind == "data_origin":
                clean_data = df
                print(f"ASIN={asin} 关键词={keyword} 检测到 ROI 表，直接使用 data_origin 作为数据源。")
            else:
                clean_data = await save_cleaned_data_orign_to_excel(df, keyword, asin)
            target_monthly = await save_top5_market_capacity_to_excel(clean_data, keyword, asin)
            review_interval = await save_review_interval_analysis_to_excel(clean_data, keyword, asin)
            ranking_percent = 0

            print(f"<UNK> review_interval={review_interval}")
            return {
                "asin": asin,
                "keyword": keyword,
                'review_interval': review_interval,
                "monthly_results": {keyword: target_monthly},
                "ranking_percent": ranking_percent,
            }
        except Exception as e:
            print(f"警告: ASIN={asin} 关键词={keyword} 处理失败，已跳过: {e}")
            return None

    keyword_tasks = [
        process_one_keyword(asin, kw, products)
        for asin, kw_map in nested_result.items()
        for kw, products in kw_map.items()
    ]
    if not keyword_tasks:
        print(
            f"警告：未加载到任何关键词 Excel 数据（请确认 xlsx 在 {FILE_DATA_ROOT}/{{ASIN}}/{{关键词}}/ 下，"
            f"且从脚本/项目目录运行）。"
        )
    monthly_results_raw = await asyncio.gather(*keyword_tasks, return_exceptions=True)
    monthly_results = []
    for item in monthly_results_raw:
        if isinstance(item, Exception):
            print(f"警告: 关键词任务异常: {item}")
            continue
        if item:
            monthly_results.append(item)
    print(monthly_results, "wangxian1")

    info_dict = await async_return_info(asin_dict=keyword_dict, info_list=monthly_results)
    print(info_dict, "ppppp")

    target_monthly_sales: Dict[str, Dict[str, float]] = {}
    for res in monthly_results:
        if not res:
            continue
        a = res["asin"]
        target_monthly_sales.setdefault(a, {}).update(res["monthly_results"])
    print(target_monthly_sales)

    monthly_sales_dict = await get_month_number(target_asins, target_monthly_sales, keyword_dict)
    print(monthly_sales_dict)
    emit_progress(f'关键词 Excel 处理完成，开始生成 ROI-US-pack（0/{len(target_asins)}）…')

    async def save_roi_safe(
        asin: str,
        node_label_path: str,
        info: dict,
        path: str,
        up_val,
        hd_val,
    ):
        try:
            hints = build_local_product_hints(nested_result, asin)
            result = await save_roi_us_pack(
                node_label_path,
                fba_info_dict,
                asin,
                asin_cpc,
                monthly_sales_dict,
                tokens,
                path,
                parity,
                info,
                unit_purchase_override=up_val,
                head_distance_override=hd_val,
                local_hints=hints,
                refund_cache=refund_cache,
            )
            return result
        except Exception as e:
            if is_seller_account_banned_error(e):
                raise
            err = f'{type(e).__name__}: {e}'
            print(f"警告: ASIN {asin} ROI-US-pack 生成失败: {e}，尝试强制写入默认值…")
            try:
                return await force_write_minimal_roi_us_pack(asin, exchange_rate=parity)
            except Exception as e2:
                roi_failures.append({'asin': asin, 'error': f'{err}; 兜底失败: {e2}'})
                emit_progress(f'失败 {asin}：{e2}')
                print(f"警告: ASIN {asin} 强制生成 ROI-US-pack 仍失败: {e2}")
                return None

    # ========== 5. 并发生成每个 ASIN 的 ROI 表（单个 ASIN 缺数据则跳过，不中断整批）==========
    roi_tasks = []
    roi_task_asins: list[str] = []
    for asin in target_asins:
        asin_key = str(asin).strip().upper()
        info = dict(asin_info_dict.get(asin_key) or {})
        if not info:
            print(f"警告: ASIN {asin_key} 无卖家精灵 advertisement 数据，将用默认值生成 ROI-US-pack")
            emit_progress(f'提示 {asin_key}：无广告接口数据，使用默认值生成 ROI 表')
        path = asin_to_image_path.get(asin_key, "")
        co = (cost_overrides or {}).get(asin) or (cost_overrides or {}).get(asin_key) or {}
        up = pd.to_numeric(co.get('unit_purchase'), errors='coerce') if isinstance(co, dict) else np.nan
        hd = pd.to_numeric(co.get('head_distance'), errors='coerce') if isinstance(co, dict) else np.nan
        up_val = None if pd.isna(up) else float(up)
        hd_val = None if pd.isna(hd) else float(hd)
        roi_task_asins.append(asin_key)
        roi_tasks.append(
            save_roi_safe(asin_key, asin_path_dict.get(asin_key, ""), info, path, up_val, hd_val)
        )

    if not roi_tasks:
        emit_progress('未找到可生成 ROI 的 ASIN')
        print("警告: target_asins 为空，ROI 表未生成")
        out = info_dict if isinstance(info_dict, dict) else {}
        if isinstance(out, dict):
            out['__roi_failures__'] = roi_failures
        return out

    done_count = 0
    info_result_raw = await asyncio.gather(*roi_tasks, return_exceptions=True)
    info_result = []
    for asin_key, item in zip(roi_task_asins, info_result_raw):
        if isinstance(item, Exception):
            err = f'{type(item).__name__}: {item}'
            roi_failures.append({'asin': asin_key, 'error': err})
            emit_progress(f'失败 {asin_key}：{item}')
            print(f"警告: ROI 任务异常 ({asin_key}): {item}")
            continue
        if item:
            info_result.append(item)
            done_count += 1
            emit_progress(f'进度 {done_count}/{len(roi_task_asins)}：{asin_key} ROI 已完成')
        else:
            if not any(f.get('asin') == asin_key for f in roi_failures):
                roi_failures.append({'asin': asin_key, 'error': 'ROI-US-pack 生成失败'})
    print(info_result, 'wangxian2')

    merging_data = await async_merging_data(info_result, info_dict)
    if not isinstance(merging_data, dict):
        merging_data = {}
    merging_data['__roi_failures__'] = roi_failures
    ok_n = len(info_result)
    fail_n = len(roi_failures)
    emit_progress(f'全部完成：成功 {ok_n} 个，失败 {fail_n} 个')
    if roi_failures:
        for row in roi_failures[:15]:
            emit_progress(f"  失败 {row.get('asin')}: {row.get('error')}")
        if len(roi_failures) > 15:
            emit_progress(f'  … 另有 {len(roi_failures) - 15} 个失败 ASIN')
    print(merging_data, 'www')
    print("所有表创建完成！")
    return merging_data


if __name__ == "__main__":
    asyncio.run(seller_wizard_main(6.88))
