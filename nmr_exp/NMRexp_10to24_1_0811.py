"""
Disclaimer: This code was written by chemists, not computer scientists
It may not look elegant, but it runs
"""


import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor
from PyPDF2 import PdfReader, PdfWriter
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from collections import defaultdict
import fitz  # PyMuPDF
import requests
import csv
from rdkit import Chem
import pandas as pd
import subprocess
from Translator import Translator
import numpy as np
import re
from unidecode import unidecode
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import ast
from concurrent.futures import ProcessPoolExecutor
import tqdm
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor

from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

print('start')

start_time = time.time()

work_dir = r"/internfs/wangjunjie/nmr_si/nmr_result_all_0716"


# 定义输入和输出文件夹
input_dir = os.path.join(work_dir, "SI_pdf")

output_dir = os.path.join(work_dir, "SI_pdf_split")


"""
your cpus for parallel processing
"""

max_works = 60



"""
# In order to minimize the computational cost of layout detection,
# only pages that contain the keyword "NMR" are selected for processing.
"""


total_pdf_num = len(os.listdir(input_dir))
curr_pdf_num = 0

def process_pdf(filename):
    """处理单个 PDF 文件：保留所有含有 'NMR' 的页面，合并成一个新的 PDF 文件"""
    global curr_pdf_num

    if not filename.lower().endswith(".pdf"):
        return
    pdf_path = os.path.join(input_dir, filename)
    try:
        pdf_reader = PdfReader(pdf_path)
        num_pages = len(pdf_reader.pages)
        print(f"Processing '{filename}' with {num_pages} pages.")

        pdf_writer = PdfWriter()  # 用于保存所有含有 'NMR' 的页面

        # 遍历每一页，检测是否包含 "NMR"
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            page_text = page.extract_text() or ""
            if "NMR" in page_text:
                pdf_writer.add_page(page)

        # 如果有至少一页包含 "NMR"，则保存成一个新的 PDF 文件
        if len(pdf_writer.pages) > 0:
            base_name = os.path.splitext(filename)[0]
            output_filename = f"{base_name}_NMR.pdf"  # 输出文件名增加后缀
            output_path = os.path.join(output_dir, output_filename)
            with open(output_path, "wb") as output_file:
                pdf_writer.write(output_file)
            print(f"Saved new PDF '{output_filename}' with {len(pdf_writer.pages)} pages.")
        else:
            print(f"No pages with 'NMR' found in '{filename}', no output file created.")

        print(f"Finished processing '{filename}'.")

        curr_pdf_num += 1
        print(f"当前进度：{curr_pdf_num}/{total_pdf_num}")

    except Exception as e:
        print(f"Error processing '{filename}': {e}")

# 获取所有待处理的 PDF 文件
pdf_files = os.listdir(input_dir)
# 使用 20 线程同时进行处理
with ProcessPoolExecutor(max_workers=max_works) as executor:
    executor.map(process_pdf, pdf_files)
time.sleep(3)





"""
run layout detection
you can change the host to your own layout detection server
"""


# ---------------------------
# 基本配置
# ---------------------------
host = "your layout detection server"  # 注意：需要加上协议头 http://
trigger_url = f"{host}/trigger-file-async"    # 提交文件解析任务接口
get_formatted_url = f"{host}/get-formatted"     # 获取格式化结果接口
get_result_url = f"{host}/get-result"           # 根据 token 获取最终解析结果接口

sync = True  # 同步模式（同步时会等待解析完成后返回）

# 输入PDF所在目录
pdf_dir = os.path.join(work_dir, "SI_pdf_split")
json_dir = os.path.join(work_dir, "SI_json")

if not os.path.exists(json_dir):
    os.makedirs(json_dir)

# 用于存放初步提交返回结果的目录
results_dir = os.path.join(json_dir, "results")
if not os.path.exists(results_dir):
    os.makedirs(results_dir)

# 用于存放格式化解析结果的目录
formatted_output_dir = os.path.join(json_dir, "other_output")
if not os.path.exists(formatted_output_dir):
    os.makedirs(formatted_output_dir)

# ---------------------------
# 提交任务时的解析配置
# ---------------------------
semantic_cfg = {
    'textual': True,
    'chart': False,
    'table': False,
    'molecule': True,
    'equation': True,
    'figure': False,
    'expression': True,
}
extra_cfg = {}

# ---------------------------
# 定义函数：获取最终解析结果（/get-result）
# ---------------------------
def get_parsing_result(token):
    data = {
        "token": token,
        "return_half": False,
        "content": True,
        "objects": True,
        "pages_dict": False
    }
    try:
        response = requests.post(get_result_url, json=data)
        if response.status_code == 200:
            result_json = response.json()
            return result_json
        else:
            print(f"获取解析结果失败，状态码：{response.status_code}")
            return None
    except Exception as e:
        print(f"获取 token {token} 解析结果时出错：{e}")
        return None

# ---------------------------
# 主流程：遍历 PDF 文件并依次提交解析任务，获取格式化结果和最终解析结果
# ---------------------------
# for filename in os.listdir(pdf_dir):

def get_layout_pdf(filename):
    if filename.lower().endswith('.pdf'):
        file_path = os.path.join(pdf_dir, filename)
        print(f"正在处理文件：{filename}")
        
        # 构造 token，要求满足正则 r'^[-\._?=&a-zA-Z0-9]{1,128}$'
        token = os.path.splitext(filename)[0]
        
        # 构造提交任务时的参数
        data = {
            'token': token,
            'sync': sync,
        }
        data.update(semantic_cfg)
        data.update(extra_cfg)
        
        # ---------------------------
        # 提交 PDF 文件解析任务
        # ---------------------------
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(trigger_url, files=files, data=data)
            submission_result = response.json()
            
            # 将提交返回的JSON保存为文件，文件名格式：原文件名_submission.json
            json_filename = os.path.splitext(filename)[0] + "_submission.json"
            json_path = os.path.join(formatted_output_dir, json_filename)
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(submission_result, jf, indent=4, ensure_ascii=False)
            
            print(f"提交结果已保存至：{json_filename}")
        except Exception as e:
            print(f"提交 {filename} 时出错：{e}")
        # 出错则跳过后续步骤
            return
        
        # ---------------------------
        # 等待一段时间，确保解析任务启动/完成（视具体情况可调整等待时长）
        # ---------------------------
        time.sleep(1)
        
        # ---------------------------
        # 获取格式化解析结果（html、latex、markdown、plain、markup）
        # ---------------------------
        base_data = {'token': token}
        for formatted in ['markup']:
            semantic_formatted = {
                'textual': formatted,
                'chart': formatted,
                'table': formatted,
                'molecule': formatted,
                'equation': formatted,
                'figure': formatted,
                'expression': formatted,
            }
            data_formatted = base_data.copy()
            data_formatted.update(semantic_formatted)
            print(f"请求 {token} 的 {formatted} 格式解析结果，参数：{data_formatted}")
            
            try:
                res = requests.post(get_formatted_url, json=data_formatted)
                if res.status_code != 200:
                    print(f"获取 {formatted} 格式结果失败，状态码：{res.status_code}")
                    continue

                # 根据不同格式设置文件头、尾和扩展名
                head, tail = '', ''
                suffix = ''
                if formatted == 'latex':
                    head = '\\documentclass{article}\n\n\\usepackage{booktabs}\n\n\\begin{document}\n'
                    tail = '\\end{document}'
                    suffix = 'tex'
                elif formatted == 'html':
                    head = '<html>\n\n<body>\n'
                    tail = '</body>\n\n</html>'
                    suffix = 'html'
                elif formatted == 'markdown':
                    suffix = 'md'
                elif formatted == 'plain':
                    suffix = 'plain'
                elif formatted == 'markup':
                    suffix = 'txt'
                else:
                    suffix = formatted

                output_filename = f"{token}-parser.{suffix}"
                output_file_path = os.path.join(formatted_output_dir, output_filename)
                with open(output_file_path, "w", encoding="utf-8") as outf:
                    if head:
                        outf.write(head + '\n')
                    try:
                        content = res.json().get('content', '')
                        outf.write(content)
                    except Exception as e:
                        print(f"写入 {formatted} 格式内容时出错：{e}")
                    if tail:
                        outf.write(tail + '\n')
                print(f"{formatted} 格式解析结果已保存至：{output_filename}")
            except Exception as e:
                print(f"获取 {formatted} 格式结果时出错：{e}")
        
        # ---------------------------
        # 调用 /get-result 接口，根据 token 获取最终解析结果
        # ---------------------------
        print(f"正在获取最终解析结果，token：{token}")
        result_data = get_parsing_result(token)
        if result_data:
            result_json_filename = os.path.splitext(filename)[0] + "_result.json"
            result_json_path = os.path.join(results_dir, result_json_filename)
            with open(result_json_path, "w", encoding="utf-8") as rf:
                json.dump(result_data, rf, indent=4, ensure_ascii=False)
            print(f"最终解析结果已保存至：{result_json_filename}")
        else:
            print(f"未能获取 token {token} 的最终解析结果")

# 获取所有待处理的 PDF 文件
pdf_files = os.listdir(pdf_dir)

# 使用 8 线程同时进行处理
with ThreadPoolExecutor(max_workers=8) as executor:
    executor.map(get_layout_pdf, pdf_files)

time.sleep(3)







"""
get the original text from the pdf
use the bbox to extract the text
"""

def extract_text_from_bbox(pdf_path, page_number, norm_bbox):
    """
    从指定 PDF 的某一页中提取指定归一化坐标区域内的文本
    参数：
        pdf_path: PDF 文件路径
        page_number: 页码（从 0 开始）
        norm_bbox: 归一化坐标 [left, top, right, bottom]
                坐标值均为相对于页面尺寸的比例，其中 top 与 bottom 均以页面顶部为参考
    返回：
        裁剪区域内提取的文本字符串
    """
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_number)
    page_rect = page.rect  # 获取页面区域
    page_width, page_height = page_rect.width, page_rect.height

    left, top, right, bottom = norm_bbox

    # 转换为实际坐标
    x0 = (left-0.002) * page_width
    y0 = top * page_height
    x1 = (right+0.002) * page_width
    y1 = bottom * page_height

    # 定义裁剪区域
    clip_rect = fitz.Rect(x0, y0, x1, y1)
    text = page.get_text(clip=clip_rect)
    doc.close()
    return text


def json_paragraph_update_from_pdf(json_in_path, pdf_path, json_out_path):
    """
    读取 JSON 文件，对其中所有 class 为 "paragraph" 的对象，
    根据其 float_xyxy 和 page 信息调用 extract_text_from_bbox 提取 PDF 中的文本，
    并将原来的 str 字段替换为最新的文本。
    
    参数：
        json_in_path: 输入 JSON 文件路径
        pdf_path: PDF 文件路径
        json_out_path: 输出 JSON 文件路径
    """
    with open(json_in_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 遍历所有对象，找到需要替换的段落
    for obj in data.get("objects", []):
        if obj.get("class") == "paragraph":
            norm_bbox = obj.get("float_xyxy")
            if norm_bbox:
                # JSON 中的页码通常从 1 开始，需要转换为 0-based 索引
                page_number = obj.get("page", 1)
                new_text = extract_text_from_bbox(pdf_path, page_number, norm_bbox)
                obj["str"] = new_text  # 更新为从 PDF 中提取的新文本
    
    with open(json_out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def process_file(json_file, json_from_dir, pdf_dir, json_to_dir):
    """
    处理单个 JSON 文件对应的 PDF 文本提取与更新操作
    """
    if json_file.endswith('.json'):
        json_in_path = os.path.join(json_from_dir, json_file)
        pdf_file = json_file.replace('_result.json', '.pdf')
        pdf_path = os.path.join(pdf_dir, pdf_file)
        json_out_path = os.path.join(json_to_dir, json_file)
        json_paragraph_update_from_pdf(json_in_path, pdf_path, json_out_path)
        print(f"已处理文件：{json_file}")

def multi_json_trans_ocr(work_dir):
    """
    遍历工作目录下的 JSON 文件，并启动最多 100 个任务并行处理
    """
    json_from_dir = os.path.join(work_dir, 'SI_json', 'results')
    pdf_dir = os.path.join(work_dir, 'SI_pdf_split')
    json_to_dir = os.path.join(work_dir, 'SI_json', 'results_para_updated')
    if not os.path.exists(json_to_dir):
        os.makedirs(json_to_dir)
    
    json_files = [f for f in os.listdir(json_from_dir) if f.endswith('.json')]
    
    # 使用 ProcessPoolExecutor 并行处理，最多同时 100 个任务
    with ProcessPoolExecutor(max_workers=max_works) as executor:
        futures = [executor.submit(process_file, json_file, json_from_dir, pdf_dir, json_to_dir)
                for json_file in json_files]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print("处理文件时出错：", e)

if __name__ == "__main__":
    multi_json_trans_ocr(work_dir)







"""
then sort the objects by the position
after this you can pair the text with the molecule 
"""




# 输入文件夹和输出文件夹路径
in_path = os.path.join(work_dir, "SI_json/results_para_updated")
out_path = os.path.join(work_dir, "SI_json/results_processed")

if not os.path.exists(out_path):
    os.makedirs(out_path)

# 允许保留的对象类别
allowed_classes = {"paragraph", "molecule", "expression", "title"}

def sort_objects_by_position(objs):
    """
    对传入对象列表（每个对象含有 "float_xyxy" 坐标，格式：[left, top, right, bottom]）进行排序：
    - 先按顶部坐标 (float_xyxy[1]) 升序排序
    - 将具有纵向交集的对象分为同一行，并在行内按左边界 (float_xyxy[0]) 升序排序
    - 最后按行的顶部坐标从上到下排列，返回排序后的对象列表
    """
    # 先按顶部坐标排序
    objs_sorted = sorted(objs, key=lambda o: o["float_xyxy"][1])
    
    rows = []  # 每一项为一行，对象列表
    for obj in objs_sorted:
        x0, y0, x1, y1 = obj["float_xyxy"]
        placed = False
        # 尝试放入已有行中：只要与该行中任一对象有纵向交集，就认为属于同一行
        for row in rows:
            # 检查当前行中是否有对象的纵坐标与当前对象交叉
            if any(max(o["float_xyxy"][1], y0) <= min(o["float_xyxy"][3], y1) for o in row):
                row.append(obj)
                placed = True
                break
        if not placed:
            rows.append([obj])
    
    # 对每一行内部按左边界排序
    for row in rows:
        row.sort(key=lambda o: o["float_xyxy"][0])
    # 对行排序：以每一行内所有对象的最小 top 值作为行的排序依据
    rows.sort(key=lambda row: min(o["float_xyxy"][1] for o in row))
    
    # 扁平化行列表
    sorted_objs = [obj for row in rows for obj in row]
    return sorted_objs

# 遍历所有json文件
for filename in os.listdir(in_path):
    if filename.endswith(".json"):
        file_in = os.path.join(in_path, filename)
        with open(file_in, "r", encoding="utf8") as f:
            data = json.load(f)
        
        # 获取所有对象，假设它们存放在 "objects" 键下
        objects = data.get("objects", [])
        # 根据 page 分组
        pages = defaultdict(list)
        for obj in objects:
            # 这里假设每个对象都有 "page" 属性，不存在时归为 None
            page = obj.get("page")
            pages[page].append(obj)
        
        # 判断哪些 page 满足条件：同时含有 "paragraph" 对象和 ("molecule" 或 "expression") 对象
        valid_pages = set()
        for page, objs in pages.items():
            has_paragraph = any(o.get("class") == "paragraph" for o in objs)
            has_mol_expr = any(o.get("class") in ("molecule", "expression") for o in objs)
            if has_paragraph and has_mol_expr:
                valid_pages.add(page)
        
        # 构造新的 objects 列表：只保留 valid_pages 中的页面，
        # 并且在每个页面内只保留 allowed_classes 的对象，再进行排序（按照规则从前到后）
        new_objects = []
        for page in sorted(valid_pages):  # 按 page 编号从小到大（或根据需要调整）
            # 筛选当前页面中允许的对象
            objs = [o for o in pages[page] if o.get("class") in allowed_classes and "float_xyxy" in o]
            # 如果有 float_xyxy 坐标，则按照规则排序
            if objs:
                sorted_objs = sort_objects_by_position(objs)
                new_objects.extend(sorted_objs)
        
        data["objects"] = new_objects

        # 保存修改后的 json 到 out_path
        file_out = os.path.join(out_path, filename)
        with open(file_out, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)



in_folder = os.path.join(work_dir, "SI_json/results_processed")
combined_folder = os.path.join(work_dir, "SI_json/results_para_conbined")
if not os.path.exists(combined_folder):
    os.makedirs(combined_folder)

for filename in os.listdir(in_folder):
    if filename.endswith(".json"):
        file_in = os.path.join(in_folder, filename)
        with open(file_in, "r", encoding="utf8") as f:
            data = json.load(f)
        
        objects = data.get("objects", [])
        new_objects = []
        i = 0
        while i < len(objects):
            obj = objects[i]
            # 如果当前对象不是 paragraph，直接保留
            if obj.get("class") != "paragraph":
                new_objects.append(obj)
                i += 1
            else:
                # 当前对象为 paragraph，准备合并连续的 paragraph 对象
                merged_str = obj.get("str", "")
                base_obj = obj.copy()  # 以第一个 paragraph 对象作为基础（其它字段保持不变）
                j = i + 1
                while j < len(objects) and objects[j].get("class") == "paragraph":
                    merged_str += objects[j].get("str", "")
                    j += 1
                base_obj["str"] = merged_str  # 更新 "str" 字段为合并后的文本
                new_objects.append(base_obj)
                i = j  # 跳过已经合并的后续 paragraph 对象
        
        data["objects"] = new_objects
        file_out = os.path.join(combined_folder, filename)
        with open(file_out, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

print("para_combine处理完成。")

time.sleep(3)



"""
then you need to extract the NMR text from a large text
first try re
if re can not do it, then use openai to do it
"""



# ---------------------------


import re
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import openai
import re

# 设置 Azure OpenAI 的 API 密钥和端点
openai.api_type = "your openai api type"
openai.api_base = "your openai api base"
openai.api_version = "your openai api version"
openai.api_key = "your openai api key"

# 设置模型名称和部署名称
model_name = "gpt-4o-mini"
deployment_name = "gpt-4o-mini"

# 定义一个全局信号量，限制 openai API 并发调用最多为 5 个
openai_api_semaphore = threading.Semaphore(13)

def nmr_text_process_gpt(input_text):
    # print(f"当前活跃线程数: {threading.active_count()}")    
    input_content_front = """
You need to extract all NMR information from the provided text and organize it in a structured format.
NMR_type: (NMR type here)  
NMR_frequency: (NMR frequency here)  
NMR_solvent: (solvent here)  
NMR_signal: (NMR signal here) 
note: (any additional notes about the spectrum here, eg. which isomer used, etc.)

If there is more than one type of NMR (e.g., proton and carbon), insert a blank line between each entry.

Instructions:
The text is OCR-generated, so there may be minor recognition errors (e.g., δ may be misrecognized as 8). Correct such errors automatically.
If no NMR data is found, respond with: no NMR
Standardize the format according to the example below.

Example1:
Input:
58% yield, white solid; M.p. 130-132 °C; 'H NMR (400 MHz, CDCl3) 8 9.02 (d, J = 2.0 Hz, 1H), 7.96-7.91 (m, 3H) 7.71 (dd,J = 9.2,2.0 Hz,1H,1.45 (s,9H); 13C{H} NMR (101 MHz,CDCl3) 8 150.3,144.8,144.1,131.9,130.5 129.6, 129.6, 128.9, 120.2, 33.8, 30.7; IR (neat) v 2958, 2906, 2864, 1464, 1363, 1203, 906, 823, 652, 571, 439 cm ; HRMS-ESI (m/z): calcd. for C13H1sNBr*: 264.03824,found: 264.03854 ([M+H]).

Output1:
NMR_type: 1H NMR  
NMR_frequency: 400 MHz  
NMR_solvent: CDCl3  
NMR_signal: 9.02 (d, J = 2.0 Hz, 1H), 7.96-7.91 (m, 3H), 7.71 (dd, J = 9.2, 2.0 Hz, 1H), 1.45 (s,9H) 
note: none

NMR_type: 13C NMR  
NMR_frequency: 101 MHz  
NMR_solvent: CDCl3  
NMR_signal: 150.3, 144.8, 144.1, 131.9, 130.5, 129.6, 129.6, 128.9, 120.2, 33.8, 30.7
note: none

Example2:
Input:
4,5,5-tetramethyl-1,3,2-dioxaborolan-2-yl)-5,6,7,8-tetrahydroquinoline

Output2:
no NMR

Example3:
compoundA 1H NMR: 8.0(d, J=3.0 Hz  2H), 7.0(d, J=3.0 Hz  2H)

Output3:
NMR_type: 1H NMR  
NMR_frequency: None
NMR_solvent: None
NMR_signal: 8.0(d, J=3.0 Hz  2H), 7.0(d, J=3.0 Hz  2H)
note: none

Now process the following text:
""" + input_text

    # 限制 openai API 并发调用
    with openai_api_semaphore:
        response = openai.ChatCompletion.create(
            deployment_id=deployment_name,
            model=model_name,
            messages=[
                {"role": "user", "content": input_content_front}
            ]
        )
    
    return response.choices[0].message.content





"""
text normalization is needed before you extract the NMR text
"""

def preprocess_text_nmr_pdfplumber(text):
    # 示例：将独立的 "8 " 替换为空（也可以改成其他合适的替换，如 δ ）
    text = re.sub(r'–', '-', text)
    text = re.sub(r'~', '-', text)
    text = re.sub(r'δ', 'δ', text) 
    text = re.sub(r'', 'δ', text)
    text = re.sub(r'•', 'δ', text)
    text = re.sub(r'·', 'δ', text)
    text = re.sub(r'δ', 'δ', text)
    text = re.sub(r'𝛿', 'δ ', text)
    text = re.sub(r'!', 'δ ', text)
    text = re.sub(r'\(ppm\)', '', text)
    text = re.sub(r'\[ppm\]', ' ', text)
    text = re.sub(r'/ppm', ' ', text)
    text = re.sub(r'p.p.m.', ' ', text)
    text = re.sub(r'δ\s*H', 'δ ', text)
    text = re.sub(r'δ\s*C', 'δ ', text)
    text = re.sub(r'\s\.', '.', text)
    text = re.sub(r'Н', 'H', text)
    text = re.sub(r' G ', 'δ ', text)
    text = re.sub(r'į', 'δ', text)
    text = re.sub(r'', ' ', text)
    text = re.sub(r'С', 'C', text)
    text = re.sub(r'∂', 'δ ', text)
    text = re.sub(r'', ' ', text)
    text = re.sub(r'', 'δ ', text)

    # 符号类替换（优先处理）
    text = re.sub(r'\u2013', '-', text)     # EN DASH → 普通短横线
    text = re.sub(r'\uf02d', '-', text)       # 私有区连字符 → 标准短横线
    text = re.sub(r'\uf02e', '.', text)       # 私有区小数点 → 标准小数点

    # 温度符号标准化（原字符已正确显示）
    text = re.sub(r'\u00b0', '°', text)        # 统一温度符号格式

    # 希腊字母标准化
    text = re.sub(r'\u03b2', 'β', text)        # beta字符
    text = re.sub(r'\u03b4', 'δ', text)        # delta字符

    # 使用 re.sub 替换私有区数字（合并替换）
    private_num_map = {
        '\uf030': '0', '\uf031': '1', '\uf032': '2',
        '\uf033': '3', '\uf034': '4', '\uf035': '5',
        '\uf036': '6', '\uf037': '7', '\uf038': '8',
        '\uf039': '9'
    }
    # 构造匹配所有需要替换字符的正则表达式模式
    pattern = re.compile("|".join(map(re.escape, private_num_map.keys())))
    text = pattern.sub(lambda m: private_num_map[m.group(0)], text)

    text = re.sub(r'¹', '1', text)
    text = re.sub(r'³', '3', text)
    
    text = re.sub(r'ppm', ' ', text)
    text = re.sub(r'', '-', text)
    text = re.sub(r'\s*"\s*', ' ', text)
    text = re.sub(r"\s*'\s*", ' ', text)
    text = re.sub(r'δ\s*=\s*', 'δ ', text)
    text = re.sub(r'\)[,:]\s*δ\s*', ') δ', text)  # 修改此处：转义右括号
    text = re.sub(r'δ\s*:', 'δ ', text)
    text = re.sub(r'M Hz', 'MHz', text)  
    text = re.sub(r'd =', 'δ', text)                           

    text = re.sub(r'NMF', 'NMR', text)
    text = re.sub(r'NMR:', 'NMR', text)
    text = re.sub(r"'H NMR", "1H NMR", text)
    text = re.sub(r'-NMR', ' NMR', text) 
    text = re.sub(r'13C\{H\} NMR', '13C NMR', text) 
    text = re.sub(r'13C\{1H\} NMR', '13C NMR', text)  
    text = re.sub(r'13C\{H\}-NMR', '13C NMR', text)  
    text = re.sub(r'13C\{1H\}-NMR', '13C NMR', text)
    text = re.sub(r' F NMR', '19F NMR', text)  
    text = re.sub(r' P NMR', '31P NMR', text) 
    text = re.sub(r'1H-­‐NMR', '1H NMR', text)

    text = re.sub(r'\s+', ' ', text).strip()

    # 如果逗号后面没有括号，则加上括号
    text = re.sub(r'(\dH),(?=\s*\d)', r'\1),', text)

    text = re.sub(r'\sH\sNMR', '1H NMR', text)
    text = re.sub(r'\sC\sNMR', '13C NMR', text)
    # 删除“-”前后的空格
    text = re.sub(r'\s*-\s*', '-', text)

    text = re.sub(r'NMR\s+δH\s+(\(.*?\))', r'NMR \1 δH', text)
    text = re.sub(r'NMR\s+δ\s+(\(.*?\))', r'NMR \1 δ', text)
    text = re.sub(r'NMR\s+δC\s+(\(.*?\))', r'NMR \1 δC', text)

    text = re.sub(r'/', r'', text)
    text = re.sub(r'\)\s*:', ')', text)

    text = re.sub(r'δ:', 'δ ', text)
    text = re.sub(r'\(δ, \)', 'δ ', text)
    text = re.sub(r'\(δ\s*\)', 'δ ', text)
    text = re.sub(r'\(δ \)', 'δ ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    text = re.sub(r'NMR 1H', '1H NMR', text)
    text = re.sub(r'NMR 13C', '13C NMR', text)
    text = re.sub(r'1NMR', '1H NMR', text)
    text = re.sub(r'13NMR', '13C NMR', text)
    text = re.sub(r'1H‐NMR', '1H NMR', text)
    text = re.sub(r'13C‐NMR', '13C NMR', text)
    text = re.sub(r'13C‐NMR', '13C NMR', text)
    text = re.sub(r'13C\s*\{1H\}\s*NMR', '13C NMR', text)
    text = re.sub(r'13C\s*\{H\}\s*NMR', '13C NMR', text)
    text = re.sub(r'13C\s*\{H\}\s*‐NMR', '13C NMR', text)

    text = re.sub(r'\(CDCl3, 400 MHz,\)', '(CDCl3, 400 MHz)', text)
    text = re.sub(r'\(major\s*\)', ' ', text)
    text = re.sub(r'major diastereomer', ' ', text)

    text = re.sub(r'NMR5', 'NMR', text)
    text = re.sub(r'δ \( \)', 'δ ', text)
    text = re.sub(r'δ', 'δ ', text)

    text = re.sub(r'\(CD3\)2CO', 'cd3cocd3', text)
    text = re.sub(r'\(CD3\)2SO', 'cd3socd3', text)

    return text



nmr_pattern = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)      # NMR类型，支持 'H, 1H, 13C{H}
    \s*NMR\s*                              # 后面跟上"NMR"关键字
    \(\s*(?P<nmr_frequency>\d+\s*M(?:Hz|hz)?)        # NMR频率，如 400 MHz
    \s*[,;]\s*(?P<nmr_solvent>[^)]+)\)\s*         # 溶剂信息，直到遇到右括号
    (?:[δd]\s*)?                           # 可选的OCR错误，如误把δ识别成8
    (?P<nmr_signal>
        -?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?   # 第一个信号（支持负数区间）
        (?:\s*\(\s*[^(]+\s*\))?                # 可能的括号注释
        (?:\s*(?:,|\s)\s*-?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?
            (?:\s*\(\s*[^(]+\s*\))?)*           # 后续信号（允许负数）
    )
""", re.VERBOSE)

nmr_pattern_2 = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)\s*NMR\s*
    \(\s*(?P<nmr_info>[^)]+)\)\s*        # 捕获全部信息，后续处理提取各项
        (?:[δd]\s*)?  
    (?P<nmr_signal>
        -?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?   # 第一个信号（支持负数区间）
        (?:\s*\(\s*[^(]+\s*\))?                # 可能的括号注释
        (?:\s*(?:,|\s)\s*-?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?
            (?:\s*\(\s*[^(]+\s*\))?)*           # 后续信号（允许负数）
    )
""", re.VERBOSE)

nmr_pattern_3 = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)\s*NMR\s*
    \(\s*(?P<nmr_info>[^)]+)\)\s*        # 捕获全部信息，后续处理提取各项
    (?P<nmr_signal>
        -?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?   # 第一个信号（支持负数区间）
        (?:\s*\(\s*[^(]+\s*\))?                # 可能的括号注释
        (?:\s*(?:,|\s)\s*-?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?
            (?:\s*\(\s*[^(]+\s*\))?)*           # 后续信号（允许负数）
    )
""", re.VERBOSE)


# 先提取出 type/info/signal 原文
extract_pat = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)   # 核素
    \s* NMR \s*
    (?P<nmr_signal>                                             # signal 原文（到行尾或分号前）
       [\s\S]+
    )
""", re.VERBOSE)

nmr_no_info = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)\s*NMR\s*δ\s*  
    (?P<nmr_signal>
        -?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?   # 第一个信号（支持负数区间）
        (?:\s*\(\s*[^(]+\s*\))?                # 可能的括号注释
        (?:\s*(?:,|\s)\s*-?\d+(?:\.\d+)?(?:--?\d+(?:\.\d+)?)?
            (?:\s*\(\s*[^(]+\s*\))?)*           # 后续信号（允许负数）
    )
""", re.VERBOSE)


nmr_need_gpt_pattern = re.compile(r"""
    (?P<nmr_type>'H|1H|F|19F|Si|29Si|B|11B|P|31P|13C(?:\{H\})?)\s*NMR\s*
    # \(\s*(?P<nmr_info>(?=[^)]*M(?:Hz|hz)?)[^)]+)\)\s*
    (?P<nmr_signal>
        [\s\S]+
    )
""", re.VERBOSE)


def is_valid_nmr(text: str) -> bool:
    m = extract_pat.search(text)
    if not m:
        return False   # 连基本格式都不合
    signal = m.group("nmr_signal")
    outside = re.sub(r'\([^)]*\)', '', signal)
    # 如果 signal 里出现了浮点数，就认为合理
    if re.search(r"\d+\.\d+", outside):
        return True
    return False
                                  


def nmr_text_process(text):
    text = preprocess_text_nmr_pdfplumber(text)
    matches = list(nmr_pattern.finditer(text))
    if not matches:
        matches = list(nmr_pattern_2.finditer(text))
        if not matches:
            matches = list(nmr_pattern_3.finditer(text))
            if not matches:
                if is_valid_nmr(text):
                    matches = list(nmr_no_info.finditer(text))
                    if not matches:
                        matches = list(nmr_need_gpt_pattern.finditer(text))
                        if not matches:
                            return "no NMR"
                        else:   
                            print(f"需要GPT处理的NMR信息：{text}")
                            gpt_response = nmr_text_process_gpt(text)
                            if gpt_response:
                                return gpt_response
                            else:
                                return "no NMR"
                            
                    output_lines = []
                    for m in matches:

                        nmr_type = m.group("nmr_type")
                        nmr_signal = m.group("nmr_signal")
                        
                        # 将多个连续空格替换为一个空格
                        nmr_signal = re.sub(r'\)\s+(?=\d)', '), ', nmr_signal)
                        
                        output_lines.append(f"NMR_type: {nmr_type} NMR")
                        output_lines.append(f"NMR_frequency: None")
                        output_lines.append(f"NMR_solvent: None")
                        output_lines.append(f"NMR_signal: {nmr_signal}")
                        output_lines.append("")  # 空行分隔不同NMR信息

                    return "\n".join(output_lines).strip()

            output_lines = []
            for m in matches:
                nmr_info = m.group("nmr_info")
                info_items = [item.strip() for item in re.split(',|;', nmr_info)]
                nmr_type = m.group("nmr_type")
                nmr_freq = next((item for item in info_items if "MHz" in item or "M" in item), None)
                nmr_solvent =  next((item for item in info_items if "d" or "D" in item), None)
                nmr_signal = m.group("nmr_signal")
                
                # 将多个连续空格替换为一个空格
                nmr_signal = re.sub(r'\)\s+(?=\d)', '), ', nmr_signal)
                
                output_lines.append(f"NMR_type: {nmr_type} NMR")
                output_lines.append(f"NMR_frequency: {nmr_freq}")
                output_lines.append(f"NMR_solvent: {nmr_solvent}")
                output_lines.append(f"NMR_signal: {nmr_signal}")
                output_lines.append("")  # 空行分隔不同NMR信息

            return "\n".join(output_lines).strip()

        output_lines = []
        for m in matches:
            nmr_info = m.group("nmr_info")
            info_items = [item.strip() for item in re.split(',|;', nmr_info)]
            nmr_type = m.group("nmr_type")
            nmr_freq = next((item for item in info_items if "MHz" in item or "M" in item), None)
            nmr_solvent =  next((item for item in info_items if "d" or "D" in item), None)
            nmr_signal = m.group("nmr_signal")
            
            # 将多个连续空格替换为一个空格
            nmr_signal = re.sub(r'\)\s+(?=\d)', '), ', nmr_signal)
            
            output_lines.append(f"NMR_type: {nmr_type} NMR")
            output_lines.append(f"NMR_frequency: {nmr_freq}")
            output_lines.append(f"NMR_solvent: {nmr_solvent}")
            output_lines.append(f"NMR_signal: {nmr_signal}")
            output_lines.append("")  # 空行分隔不同NMR信息
        
        return "\n".join(output_lines).strip()
    
    output_lines = []
    for m in matches:
        nmr_type = m.group("nmr_type")
        nmr_freq = m.group("nmr_frequency")
        nmr_solvent = m.group("nmr_solvent").strip()
        nmr_signal = m.group("nmr_signal")
        
        # 将多个连续空格替换为一个空格
        nmr_signal = re.sub(r'\)\s+(?=\d)', '), ', nmr_signal)
        
        output_lines.append(f"NMR_type: {nmr_type} NMR")
        output_lines.append(f"NMR_frequency: {nmr_freq}")
        output_lines.append(f"NMR_solvent: {nmr_solvent}")
        output_lines.append(f"NMR_signal: {nmr_signal}")
        output_lines.append("")  # 空行分隔不同NMR信息

    return "\n".join(output_lines).strip()




"""
we use translator to replace the abbrevations of smiles
for details, see: https://arxiv.org/abs/2411.11098
"""


with_NMR_but_no_NMR = []

translator = Translator()

def process_single_file(file_path, directory):
    print(f"正在处理文件：{file_path}")
    filename = os.path.basename(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"读取 {file_path} 时出错: {e}")
        return

    objects = data.get("objects", [])
    
    # 如果没有 molecule 或 paragraph 对象，则跳过
    if not any(obj.get("class") == "molecule" for obj in objects):
        return
    if not any(obj.get("class") == "paragraph" for obj in objects):
        return

    # 遍历所有 paragraph 对象，调用 nmr_text_process
    new_objects = []
    for i, obj in enumerate(objects):
        if obj.get("class") == "paragraph" and "str" in obj:
            if "NMR" in obj["str"]:
                original_text = obj["str"]
                processed_text = nmr_text_process(original_text)
                if processed_text == "no NMR":
                    with_NMR_but_no_NMR.append({"ERROR": original_text})
                obj["str"] = processed_text

            new_objects.append(obj)
        
        elif obj.get("class") == "molecule" and "str" in obj:
            if "sep" in obj["str"]:
                smi = obj["str"]
                try:
                    new_smi = translator.refactor(smi).smi
                    mol = Chem.MolFromSmiles(new_smi)
                    if mol is None:
                        new_smi = smi
                except Exception as e:
                    print(f"翻译 SMILES 时出错: {e}")
                    new_smi = smi
                obj["str"] = new_smi
                new_objects.append(obj)
            else:
                new_objects.append(obj)
            
        elif obj.get("class") == "title":
            continue  
        
        else:
            new_objects.append(obj)

    data["objects"] = new_objects

    # 保存处理后的数据，新文件名为原文件名加 '_processed'
    base_name, ext = os.path.splitext(filename)
    new_filename = base_name + "_processed" + ext
    output_dir = os.path.join(work_dir, "SI_json", "final_results")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    new_file_path = os.path.join(output_dir, new_filename)
    with open(new_file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"已处理文件并保存为: {new_file_path}")

def process_json_files(directory):
    total_num = len([f for f in os.listdir(directory) if f.endswith('.json')])
    done_num = 0
    print("开始处理 JSON 文件...")
    json_files = [os.path.join(directory, filename) 
                for filename in os.listdir(directory) if filename.endswith(".json")]
    
    with ThreadPoolExecutor(max_workers=max_works) as executor:
        future_to_file = {}
        # 先提交前 max_workers 个任务
        for file_path in json_files[:max_works]:
            future = executor.submit(process_single_file, file_path, directory)
            future_to_file[future] = file_path
        
        next_file_index = max_works
        # 当任务完成后，再提交新任务，直到所有文件处理完毕
        while future_to_file:
            for future in as_completed(list(future_to_file)):
                file_path = future_to_file.pop(future)
                try:
                    future.result()  # 如果任务中有异常，这里会抛出
                except Exception as exc:
                    print(f"{file_path} 处理时产生异常: {exc}")
                # 如果还有文件未提交，则提交一个新的任务
                if next_file_index < len(json_files):
                    done_num += 1
                    print(f"已处理 {done_num}/{total_num} 个文件")
                    new_file_path = json_files[next_file_index]
                    next_file_index += 1
                    new_future = executor.submit(process_single_file, new_file_path, directory)
                    future_to_file[new_future] = new_file_path

if __name__ == '__main__':
    directory = os.path.join(work_dir, "SI_json", "results_para_conbined")
    process_json_files(directory)
    
    time.sleep(5)













"""
we find that some of the sort is not correct
so we need to sort the objects by the position again
"""

from_json_dir = os.path.join(work_dir, "SI_json/final_results")
out_json_dir = os.path.join(work_dir, "SI_json/final_results_copy")

allowed_classes = {"paragraph", "molecule", "expression", "title"}

def sort_objects_by_position_updated(objs):
    """
    对传入对象列表（每个对象含有 "float_xyxy" 坐标，格式：[left, top, right, bottom]）进行排序：
    - 先按顶部坐标 (float_xyxy[1]) 升序排序
    - 将具有纵向交集的对象分为同一行（但每个 bbox 的 y 范围会被收缩 ±0.01）
    - 行内按 bbox 中心横坐标排序
    - 行之间按最小 top 排序
    - 返回排序后的对象列表
    """
    objs_sorted = sorted(objs, key=lambda o: o["float_xyxy"][1])  # 按 top 排序

    rows = []
    for obj in objs_sorted:
        x0, y0, x1, y1 = obj["float_xyxy"]
        placed = False
        for row in rows:
            for o in row:
                # 收缩后的 y 范围比较
                y0a, y1a = o["float_xyxy"][1] + 0.01, o["float_xyxy"][3] - 0.01
                y0b, y1b = y0 + 0.01, y1 - 0.01
                if max(y0a, y0b) <= min(y1a, y1b):
                    row.append(obj)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            rows.append([obj])

    # 行内按中心横坐标排序
    for row in rows:
        row.sort(key=lambda o: (o["float_xyxy"][0] + o["float_xyxy"][2]) / 2)

    # 行排序（仍用原始的 top）
    rows.sort(key=lambda row: min(o["float_xyxy"][1] for o in row))

    return [obj for row in rows for obj in row]


def process_file_updating(filename):
    file_in = os.path.join(from_json_dir, filename)
    file_out = os.path.join(out_json_dir, filename)

    try:
        with open(file_in, "r", encoding="utf8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取 {filename} 时出错: {e}")
        return

    objects = data.get("objects", [])
    pages = defaultdict(list)
    for obj in objects:
        page = obj.get("page")
        pages[page].append(obj)

        if "type" in obj:
            obj["class"] = obj.pop("type")
        if "text" in obj:
            obj["str"] = obj.pop("text")
        if "caption" in obj:
            obj["str"] = obj.pop("caption")

    valid_pages = set()
    for page, objs in pages.items():
        has_paragraph = any(o.get("class") == "paragraph" for o in objs)
        has_mol_expr = any(o.get("class") in ("molecule", "expression") for o in objs)
        if has_paragraph and has_mol_expr:
            valid_pages.add(page)

    new_objects = []
    for page in sorted(valid_pages):
        objs = [o for o in pages[page] if o.get("class") in allowed_classes and "float_xyxy" in o]
        if objs:
            sorted_objs = sort_objects_by_position_updated(objs)
            new_objects.extend(sorted_objs)

    data["objects"] = new_objects

    try:
        with open(file_out, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"写入 {filename} 时出错: {e}")

os.makedirs(out_json_dir, exist_ok=True)

all_files = [f for f in os.listdir(from_json_dir) if f.endswith(".json")]

with ProcessPoolExecutor(max_workers=60) as executor:
    list(tqdm(executor.map(process_file_updating, all_files), total=len(all_files)))








"""
now pair the text with the molecule and NMR text
"""


# 定义存放结果的列表
results = []

# 目标文件夹路径
folder = os.path.join(work_dir, "SI_json/final_results_copy")

H_NMR = "False"
C_NMR = "False"
active_elements = {7, 8, 16}  # N, O, S

def count_hydrogens(nmr_data: str) -> float:
    # 按空行分块，假设不同NMR数据之间以空行分隔
    blocks = nmr_data.strip().split("\n\n")
    total_h = 0.0
    for block in blocks:
        # 只处理1H NMR的块
        if "1H NMR" in block:
            # 提取NMR_signal: 后面的部分
            signal_match = re.search(r"NMR_signal:\s*(.*)", block)
            if signal_match:
                signal_text = signal_match.group(1)
                # 匹配整数或小数，且H可以是拉丁字母H或者西里尔字母Н
                matches = re.findall(r"(\d+(?:\.\d+)?)\s*[HН]\b", signal_text)
                total_h += sum(float(num) for num in matches)
                if isinstance(total_h, float) and total_h.is_integer():
                    total_h = int(total_h)
    return total_h

def have_1H_nmr(nmr_data: str) -> int:
    if "H NMR" in nmr_data:
        H_NMR = "True"
    else:
        H_NMR = "False"
    return H_NMR

def have_13C_nmr(nmr_data: str) -> int:
    if "C NMR" in nmr_data:
        C_NMR = "True"
    else:
        C_NMR = "False"
    return C_NMR

total_index = 0

error_smiles = []


lock = threading.Lock()

def process_file(file):
    """处理单个 JSON 文件，返回本地结果和错误 smiles 以及本地计数增量"""
    local_results = []
    local_errors = []
    obj_index = 0

    filepath = os.path.join(folder, file)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if "objects" not in data:
        return local_results, local_errors

    for obj in data["objects"]:
        # 判定 category
        if "type" in obj:
            category = obj["type"]
        elif "class" in obj:
            category = obj["class"]
        else:
            category = "unknown"

                
        # 处理 molecule 类型
        if category == "molecule":
            
            if "str" in obj:
                text = obj["str"]
                page_in_file = obj.get("page", 0)
                location_in_page = obj.get("float_xyxy", [0, 0, 0, 0])
                obj_index += 1
                # 利用正则提取 \begin{molecule} 和 \end{molecule} 之间的内容
                match = re.search(r"\\begin\{molecule\}\s*(.*?)\s*\\end\{molecule\}", text, re.DOTALL)
                if match:
                    smiles = match.group(1).strip()

                else:
                    smiles = text

                # 利用 RDKit 解析 SMILES 并计算氢原子总数
                try:
                    mol = Chem.MolFromSmiles(smiles)
                except Exception:
                    mol = None  # 捕获所有 RDKit 异常，避免终端输出

                if mol is None:
                    h_count = 0
                    h_count_restrict = 0
                    local_errors.append(smiles)
                    smiles = "SMILES Parse Error"
                else:
                    h_count = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms())
                    #记录除去活泼氢原子之后的情况
                    h_count_restrict  = sum(
                        atom.GetTotalNumHs() for atom in mol.GetAtoms() 
                        if atom.GetAtomicNum() not in active_elements
                    )
                
                local_results.append({
                    "filename": file,
                    "category": "molecule",
                    "index": obj_index,
                    "hydrogen_count": h_count,
                    "hydrogen_count_restrict": h_count_restrict,
                    "smiles": smiles,
                    "page_in_file": page_in_file,
                    "location_in_page": location_in_page,
                })

            elif "caption" in obj:
                text = obj.get("caption", "")
                page_in_file = obj.get("page", 0)
                location_in_page = obj.get("float_xyxy", [0, 0, 0, 0])
                obj_index += 1
                # 利用正则提取 \begin{molecule} 和 \end{molecule} 之间的内容
                match = text
                if match:
                    smiles = match
                    # 利用 RDKit 解析 SMILES 并计算氢原子总数
                    try:
                        mol = Chem.MolFromSmiles(smiles)
                    except Exception:
                        mol = None  # 捕获所有 RDKit 异常，避免终端输出
                    if mol is None:
                        h_count = 0
                        h_count_restrict = 0
                        local_errors.append(smiles)
                        smiles = "SMILES Parse Error"
                    else:
                        h_count = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms())
                        #记录除去活泼氢原子之后的情况
                        h_count_restrict  = sum(
                            atom.GetTotalNumHs() for atom in mol.GetAtoms() 
                            if atom.GetAtomicNum() not in active_elements
                        )
                else:
                    h_count = 0
                    h_count_restrict = 0
                    smiles = ""
                
                local_results.append({
                    "filename": file,
                    "category": "molecule",
                    "index": obj_index,
                    "hydrogen_count": h_count,
                    "hydrogen_count_restrict": h_count_restrict,
                    "smiles": smiles,
                    "page_in_file": page_in_file,
                    "location_in_page": location_in_page,
                })

        # 处理 paragraph 类型
        elif category == "paragraph":
            if "str" in obj:
                text = obj.get("str", "")
                page_in_file = obj.get("page", 0)
                location_in_page = obj.get("float_xyxy", [0, 0, 0, 0])
                obj_index += 1
                if "NMR" not in text:
                    continue
                if "1H NMR" in text:
                    # 如果有大于等于 1 个 "1H NMR"
                    if text.count("NMR_type: 1H NMR") >= 2 or text.count("NMR_type: H NMR") >= 2:
                        text = 'error, too many NMR, maybe mixture\n' + text 
                        h_count = 0
                    else:
                        # 提取从 "NMR_type: 1H NMR" 到下一个 "NMR_type:" 或结束之间的文本
                        match = re.search(r"NMR_type:\s*1H NMR(.*?)(?:NMR_type:|$)", text, re.DOTALL)
                        if match:
                            nmr_data = text
                            h_count = count_hydrogens(nmr_data)
                        else:
                            h_count = 0
                else:
                    h_count = 0
                H_NMR = have_1H_nmr(text)
                C_NMR = have_13C_nmr(text)
                h_count_restrict = h_count
                # 统一字段，将 smiles 字段置空（或可记录其他信息）
                local_results.append({
                    "filename": file,
                    "category": "paragraph",
                    "index": obj_index,
                    "hydrogen_count": h_count,
                    "hydrogen_count_restrict": h_count_restrict,
                    "smiles": text,
                    "H_NMR": H_NMR,
                    "C_NMR": C_NMR,
                    "page_in_file": page_in_file,
                    "location_in_page": location_in_page,
                    "used": "unused"
                })
            
            elif "text" in obj:
                text = obj.get("text", "")
                page_in_file = obj.get("page", 0)
                location_in_page = obj.get("float_xyxy", [0, 0, 0, 0])
                obj_index += 1
                if "NMR" not in text:
                    continue
                if "1H NMR" in text:
                    # 如果有大于等于 1 个 "1H NMR"
                    if text.count("NMR_type: 1H NMR") >= 2 or text.count("NMR_type: H NMR") >= 2:
                        text = 'error, too many NMR, maybe mixture\n' + text 
                        h_count = 0
                    else:
                        # 提取从 "NMR_type: 1H NMR" 到下一个 "NMR_type:" 或结束之间的文本
                        match = re.search(r"NMR_type:\s*1H NMR(.*?)(?:NMR_type:|$)", text, re.DOTALL)
                        if match:
                            nmr_data = text
                            h_count = count_hydrogens(nmr_data)
                        else:
                            h_count = 0
                else:
                    h_count = 0
                H_NMR = have_1H_nmr(text)
                C_NMR = have_13C_nmr(text)
                h_count_restrict = h_count
                # 统一字段，将 smiles 字段置空（或可记录其他信息）
                local_results.append({
                    "filename": file,
                    "category": "paragraph",
                    "index": obj_index,
                    "hydrogen_count": h_count,
                    "hydrogen_count_restrict": h_count_restrict,
                    "smiles": text,
                    "H_NMR": H_NMR,
                    "C_NMR": C_NMR,
                    "page_in_file": page_in_file,
                    "location_in_page": location_in_page,
                    "used": "unused"
                })

    return local_results, local_errors

# —— 并发执行 —— #
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

json_files = [f for f in os.listdir(folder) if f.endswith('.json')]

results = []
error_smiles = []
lock = threading.Lock()

with ThreadPoolExecutor(max_workers=60) as executor:
    futures = {executor.submit(process_file, f): f for f in json_files}
    
    for future in tqdm(as_completed(futures), total=len(futures), desc="Processing JSON files"):
        local_results, local_errors = future.result()
        with lock:
            results.extend(local_results)
            error_smiles.extend(local_errors)

print(len(results))
print(f"这部分处理完成，耗时：{time.time() - start_time} 秒")

# 1. 生成 DataFrame
df = pd.DataFrame(results)

# 4) 把这个行号搬到一个叫 total_index 的列里，+1 从 1 开始
df['total_index'] = df.index + 1

def clean_text(text):
    if isinstance(text, str):
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', text)
    return text

def parallel_apply(series, func, max_workers=60, chunksize=100000):
    results = [None] * len(series)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i in range(0, len(series), chunksize):
            chunk = series.iloc[i:i+chunksize]
            futures.append((i, executor.submit(lambda c: c.apply(func), chunk)))
        
        for i, future in tqdm(futures, desc="Cleaning", total=len(futures)):
            results[i:i+chunksize] = future.result().tolist()
    return pd.Series(results, index=series.index)

# 3. 并发清洗每一列
for col in df.select_dtypes(include=['object']).columns:
    df[col] = parallel_apply(df[col], clean_text)

# 4. 保存
output_parquet = os.path.join(work_dir, "nmr_results_all_0715_updated.parquet")
df.to_parquet(output_parquet, index=False)

print(f'df 共有 {len(df)} 行')

# 保存错误 SMILES
with open(os.path.join(work_dir, "error_smiles.txt"), 'w', encoding='utf-8') as f:
    for smi in error_smiles:
        f.write(smi + '\n')

df_10000 = df.head(10000)
df_10000.to_csv(r"/internfs/wangjunjie/nmr_si/nmr_result_all/test0715_updated.csv", index=False)

print("✅ 多线程清洗完成，parquet 保存成功。")





output_parquet = os.path.join(work_dir, "nmr_results_all.parquet")

# 1. 读取 Excel 文件（请将 'input.xlsx' 替换为你的文件名）
df = pd.read_parquet(output_parquet)

# 2. 根据 filename 和 total_index 排序，确保遍历顺序正确
df = df.sort_values(by=['filename', 'total_index'])

# 用一个集合来保存符合条件的行在 df 中的索引
selected_indices = set()
                

import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 假设 df 已经定义，selected_indices 也已初始化为一个 set
# 将 df 的索引设为 total_index，这样 df 和 df_indexed 的索引一致
df.set_index('total_index', inplace=True, drop=False)
df_indexed = df  # df_indexed 就是 df 本身

# 全局锁，用于保护对 df 和 selected_indices 的修改
lock = threading.Lock()

def process_molecule(row):
    """
    对单个 molecule 行进行处理：
    1. 尝试查找 total_index + 1 位置的 paragraph 行进行匹配（先比较 hydrogen_count，再比较 hydrogen_count_restrict）
    2. 若未匹配成功，再尝试查找 total_index - 1 的 paragraph 行
    匹配成功后更新 df 中对应 paragraph 行的 used 字段，并记录 molecule 和 paragraph 的行索引。
    """
    global df, df_indexed, selected_indices, curr_num_of_mol
    mol_matched = False
    next_index = row.total_index + 1
    prev_index = row.total_index - 1
    curr_num_of_mol += 1
    if curr_num_of_mol % 10000 == 0:
        print(f"已处理 {curr_num_of_mol}/{total_num_of_molecules} 个分子")

    # 先尝试查找下一个 candidate
    with lock:
        candidate_next = df_indexed.loc[next_index] if next_index in df_indexed.index else None
    if candidate_next is not None:
        # 如果只有一行，转换为 DataFrame
        if isinstance(candidate_next, pd.Series):
            candidate_next = candidate_next.to_frame().T
        for cand in candidate_next.itertuples():
            with lock:
                # 获取当前 candidate 的 used 状态
                used_status = df.at[cand.Index, 'used']
            if cand.category == 'paragraph' and used_status == 'unused':
                # 判断 cand.hydrogen_count 不为 0 且在 [row.hydrogen_count, row.hydrogen_count_restrict] 范围内
                if cand.hydrogen_count != 0 and min(row.hydrogen_count, row.hydrogen_count_restrict) <= cand.hydrogen_count <= max(row.hydrogen_count, row.hydrogen_count_restrict):
                    with lock:
                        if df.at[cand.Index, 'used'] == 'unused':
                            df.at[cand.Index, 'used'] = 'used'
                            selected_indices.add(row.Index)
                            selected_indices.add(cand.Index)
                            mol_matched = True
                    if mol_matched:
                        return


    # 如果下一个 candidate 未匹配成功，则尝试查找前一个 candidate
    with lock:
        candidate_prev = df_indexed.loc[prev_index] if prev_index in df_indexed.index else None
    if candidate_prev is not None:
        if isinstance(candidate_prev, pd.Series):
            candidate_prev = candidate_prev.to_frame().T
        for cand in candidate_prev.itertuples():
            with lock:
                used_status = df.at[cand.Index, 'used']
            if cand.category == 'paragraph' and used_status == 'unused':
                # 判断 cand.hydrogen_count 不为 0 且在 [row.hydrogen_count, row.hydrogen_count_restrict] 范围内
                if cand.hydrogen_count != 0 and min(row.hydrogen_count, row.hydrogen_count_restrict) <= cand.hydrogen_count <= max(row.hydrogen_count, row.hydrogen_count_restrict):
                    with lock:
                        if df.at[cand.Index, 'used'] == 'unused':
                            df.at[cand.Index, 'used'] = 'used'
                            selected_indices.add(row.Index)
                            selected_indices.add(cand.Index)
                            mol_matched = True
                    if mol_matched:
                        return

# 确保 selected_indices 已经定义
selected_indices = set()

# 提取所有 category 为 'molecule' 的行，转换为元组列表以便迭代
molecule_rows = list(df[df['category'] == 'molecule'].itertuples())
total_num_of_molecules = len(molecule_rows)
print(f"共有 {total_num_of_molecules} 个分子需要处理")
curr_num_of_mol = 0

# 使用线程池并行处理，每个 molecule 行一个任务
with ThreadPoolExecutor(max_workers=max_works) as executor:
    futures = [executor.submit(process_molecule, row) for row in molecule_rows]
    for future in as_completed(futures):
        future.result()

# 处理完毕后，df 中已更新匹配的 paragraph 行的 used 字段，selected_indices 记录了所有匹配到的行索引

# 4. 从 df 中重新提取更新后的行，并去除可能重复的行
result_df = df.loc[list(selected_indices)].reset_index(drop=True)
result_df = result_df.sort_values(by="total_index", ascending=True)

# 保存到新的文件（可以修改文件名）
final_output_parquet = os.path.join(work_dir, "matched_results.parquet")
result_df.to_parquet(final_output_parquet, index=False)
print("parquet 文件已保存到", final_output_parquet)

# error_output_excel = os.path.join(work_dir, "with_NMR_but_no_NMR.xlsx")
# error_df = pd.DataFrame(with_NMR_but_no_NMR, columns=["ERROR"])
# for index, row in error_df.iterrows():
#     row['ERROR'] = clean_text(row['ERROR'])
# error_df.to_excel(error_output_excel, index=False)

finish_time = time.time()

print("处理完成，耗时：", finish_time - start_time, "秒")







"""
This step reformats the Parquet file for easier downstream processing.
"""


from io import StringIO
import csv
from concurrent.futures import ProcessPoolExecutor
import time
# from unidecode import unidecode
import pandas as pd
# import openpyxl
import os
import re
from tqdm import tqdm


input_path = os.path.join(work_dir, "matched_results.parquet")
output_path = os.path.join(work_dir, "matched_results_mol_nmr.parquet")
output_csv_path = os.path.join(work_dir, "matched_results_mol_nmr.csv")


# ------------------------------
# 第一阶段：极速预处理方案（支持超大型Excel）
# ------------------------------
def preprocess_parquet_single_thread(input_path):
    """单线程直接处理整个parquet文件"""
    print("🔄 开始单线程预处理Excel文件...")

    df = pd.read_parquet(input_path)
    headers = df.columns
    df.to_csv("temp_chunk_0.csv", index=False)
    print(f"✅ 预处理完成，已生成 1 个临时文件")


# --------------- 第二阶段：并行处理 ----------------
# 预编译正则表达式（提速关键）
NMR_TYPE_REGEX = re.compile(r"NMR_type:\s*(.*?)\s*[\r\n]", re.IGNORECASE)
FREQUENCY_REGEX = re.compile(r"NMR_frequency:\s*(.*?)\s*[\r\n]", re.IGNORECASE)
SOLVENT_REGEX = re.compile(r"NMR_solvent:\s*(.*?)\s*[\r\n]", re.IGNORECASE)
SIGNAL_REGEX = re.compile(r"NMR_signal:\s*(.*?)(?=\s*$|\s*NMR_type|\s*note)", re.DOTALL | re.IGNORECASE)
NOTE_REGEX = re.compile(r"Note:\s*(.*?)(?=\s*(?:NMR_type|$))", re.DOTALL|re.IGNORECASE)

import re

# 预编译正则表达式提升性能
SHIFT_PATTERN = re.compile(r"(\d+\.\d+)(?:-(\d+\.\d+))?")
J_VALUE_PATTERN = re.compile(
    r"J\s*=\s*((?:\d+\.?\d*[\s,]+)*\d+\.?\d*)\s*([a-zA-Z]+)",  # 修改后的正则表达式
    re.IGNORECASE
)


def parse_shift(shift_str):
    """解析化学位移范围"""
    match = SHIFT_PATTERN.search(shift_str)
    if not match:
        return (None, None)

    min_shift = max_shift = float(match.group(1))
    if match.group(2):
        shifts = sorted([float(match.group(1)), float(match.group(2))])
        min_shift, max_shift = shifts[0], shifts[1]

    # 保留两位小数
    return (round(max_shift, 2), round(min_shift, 2))



"""
This dictionary maps all NMR peak types to their standardized forms.
"""

multiplet_dict = {
    # multiplet variants
    "m": "m", "M": "m", "multiple peaks": "m", "complex": "m", "multiplet": "m",
    "multiplet peak": "m", "multiple": "m", "mc": "m", "complex m": "m", "comp m": "m",
    "comp. m": "m", "ovrlp": "m", "overlap": "m", "overlapping": "m", "overlapped": "m",
    "overlapped peak": "m", "overlapping peak": "m", "m.": "m", "m peak": "m",
    "br. m": "m", "bm": "m", "brm": "m", "br m": "m", "br.m": "m", "broad m": "m",
    "broad multiplet": "m", "broad multiplet peak": "m", "app. m": "m", "overlapping m": "m", 
    "dm": "m", "dm peak": "m", "dm. peak": "m", 
    "comp": "m", "complex": "m", "complex peak": "m", "c": "m", "tm": "m", "overlappead m": "m",
    "maasif": "m",

    # singlet
    "s": "s", "S": "s", "singlet": "s", "singlet peak": "s", 

    # doublet
    "d": "d", "doublet": "d", "doublet peak": "d", "double": "d",

    # triplet
    "t": "t", "“t”": "t",

    # quintet
    "q": "q", "quartet": "q", "quartet peak": "q",

    # pentet
    "p": "p", "penta": "p", "pent": "p", "pentet": "p", "quint": "p", "quintet": "p", "quint.": "p", "quin": "p",

    # heptet
    "hept": "hept", "heptet": "hept", "hept.": "hept", "sept": "hept", "sept.": "hept",
    "sep": "hept", "h": "hept", "septet": "hept",

    "heptd": "heptd", "heptet d": "heptd", "heptet d peak": "heptd", "heptet d peak": "heptd",

    # hex/sextet
    "hex": "hex", "hextet": "hex", "sex": "hex", "sextet": "hex", "sext": "hex", "hex.": "hex", "sx": "hex",

    # common complex patterns
    "dd": "dd", "d d": "dd", "td": "td", "t d": "td" ,"dt": "dt", "tt": "tt", "dq": "dq", "dquint": "dq",
    "qd": "qd", "qt": "qt", "tq": "tq", "dp": "dp", "pd": "pd", "tp": "tp", "pt": "pt",
    "dh": "dh", "ddd": "ddd", "dtt": "dtt", "tdd": "tdd", "dtd": "dtd", "ddt": "ddt",
    "dtq": "dtq", "tdt": "tdt", "ttd": "ttd", "dqd": "dqd", "qdd": "qdd", "ddq": "ddq",
    "spt": "spt", "dqt": "dqt", "ddp": "ddp", "dddd": "dddd", "dddt": "dddt", "ddtd": "ddtd",
    "dtdd": "dtdd", "dqq": "dqq", "hd": "hd", "oct": "oct", "dhept": "dh",

    # broad peaks
    "br": "br", "broad": "br", "br.": "br", "broad peak": "br", "b": "br", "broadened s": "br", "app br s": "br",

    "brs": "brs", "br s": "brs", "bs": "brs", "br.s": "brs", "br. s": "brs",
    "broad s": "brs", "s br": "brs", "sbr": "brs", "broad s.": "brs", "s broad": "brs",
    "broad singlet": "brs", "sb": "brs", "br. s.": "brs", "broad signal": "brs","br. s": "brs",

    "brd": "brd", "br d": "brd", "br.d": "brd", "broad d": "brd", "broad doublet": "brd",
    "broad doublet peak": "brd", "bd": "brd",

    "brt": "brt", "br t": "brt", "br.t": "brt", "broad t": "brt", "broad triplet": "brt",
    "broad triplet peak": "brt", "bt": "brt",

    "brq": "brq", "br q": "brq", "br.q": "brq", "broad q": "brq",
    "broad quintet": "brq", "broad quintet peak": "brq", "bq": "brq",

    "brdd": "brdd", "br dd": "brdd", "br.dd": "brdd", "broad dd": "brdd",
    "broad doublet doublet": "brdd", "broad doublet doublet peak": "brdd", "bdd": "brdd",

    # AB systems
    "AB": "AB", "AB q": "ABq", "ABq": "ABq", "ABX": "ABX", "ABd": "ABd",
    "AA′ BB′ ": "AA'BB'", "AA′BB′": "AA'BB'", "AA'BB'": "AA'BB'",
    "AA BB": "AA'BB'", "AA BB-system": "AA'BB'", "AA’BB’": "AA'BB'", "AB quartet": "ABq",

    "AA′BB′C": "AA'BB'C", "AA′ BB′ C": "AA'BB'C", "AA'BB'C": "AA'BB'C", "AA’BB’C:": "AA'BB'C","AB2m": "AB2m",

    # apparent (app.) multiplets
    "app s": "app s", "ap s": "app s", "apparent s": "app s", "s apparent": "app s",
    "app.s": "app s", "app. s": "app s", "app singlet": "app s", "virt.s": "app s",
    "sapp": "app s", "app. singlet": "app s", "s-like": "app s",

    "app d": "app d", "ap d": "app d", "apparent d": "app d", "d apparent": "app d",
    "app.d": "app d", "app. d": "app d", "app doublet": "app d", "virt.d": "app d",
    "dapp": "app d", "app. doublet": "app d", "d-like": "app d", "appd": "app d", "pseudo d": "app d",

    "app t": "app t", "ap t": "app t", "apparent t": "app t", "t apparent": "app t",
    "app.t": "app t", "app. t": "app t", "app triplet": "app t", "virt.t": "app t",
    "tapp": "app t", "app. triplet": "app t", "t-like": "app t", "appt": "app t", "apt": "app t",

    "app q": "app q", "ap q": "app q", "apparent q": "app q", "q apparent": "app q",
    "app.q": "app q", "app. q": "app q", "app quintet": "app q", "app. quintet": "app q",
    "virt.q": "app q", "qapp": "app q", "app. quint": "app q", "q-like": "app q", "app quint": "app q",

    "app dt": "app dt", "ap dt": "app dt", "apparent dt": "app dt", "app.dt": "app dt",
    "app. dt": "app dt", "app doublet triplet": "app dt", "virt.dt": "app dt",
    "dtapp": "app dt", "app. doublet triplet": "app dt", "dt-like": "app dt",

    "app td": "app td", "ap td": "app td", "apparent td": "app td", "app.td": "app td",
    "app. td": "app td", "app triplet doublet": "app td", "virt.td": "app td",
    "tdapp": "app td", "app. triplet doublet": "app td", "td-like": "app td",

    "app dd": "app dd", "ap dd": "app dd", "apparent dd": "app dd", "app.dd": "app dd",
    "app. dd": "app dd", "app doublet doublet": "app dd", "ddapp": "app dd",
    "virt.dd": "app dd", "app. doublet doublet": "app dd", "dd-like": "app dd",

    "app dq": "app dq", "ap dq": "app dq", "apparent dq": "app dq", "app.dq": "app dq",
    "app. dq": "app dq", "app doublet quintet": "app dq", "virt.dq": "app dq",
    "dqapp": "app dq", "app. doublet quintet": "app dq", "dq-like": "app dq",


    "app ddt": "app ddt", "ap tt": "app ddt", "apparent ddt": "app ddt", "app.ddt": "app ddt",

    "app p": "app p",

    "qq": "qq",

    "tddd": "tddd",

    "qdt": "qdt",

    "dddq": "dddq",

    "ddddd": "ddddd",
    "d x d": "dd",
    "tdq": "tdq",
    "qqd": "qqd",
    "dsept": "heptd",
    "septd": "heptd",
    "sp": "s",
    "tr": "t",
    "appt d": "app d",
    "appt t": "app t",
    "appt dt": "app dt",
    "t like": "app t",
    "like d": "app d",
    "distorted t": "app t",
    "ps t": "app t",
    "pst": "app t",
    "ps d": "app d",
    "dAB": "AB",
    "AB system": "AB",
    "dABq": "ABq",
    "A of AB quartet": "ABq",
    "B of AB quartet": "ABq",
    "d of ABq": "ABq",
    "abq": "ABq",
    "ABdd": "ABd",
    "dABsyst": "AB",
    "dAB syst": "AB",
    "ddABsyst": "AB",
    "quart": "q",
    "quartet": "q",
    "qnt": "q",
    "qi": "q",
    "aq": "q",
    "yq": "q",
    "vt": "t",
    "sl": "s",
    "sbroad": "brs",
    "b s": "brs",
    "br td": "br td",
    "br dt": "br dt",
    "dbr": "brd",
    "d br": "brd",
    "non": "nonet",
    "nonet": "nonet",
    "quintuplet": "p",
    "sextuplet": "hex",
    "app sext": "app hex",
    "apparent sextet": "app hex",
    "app qd": "app qd",
    "app tdd": "app tdd",
    "app dtd": "app dtd",
    "app d": "app d",
    "app t": "app t",
    "app p": "app p",
    "app triplet": "app t",
    "apparent triplet": "app t",
    "apparent p": "app p",
    "app br s": "brs",
    "apparent br s": "brs",
    "apparent br d": "brd",
    "overlapped d": "d",
    "mult": "m",
    "om": "m",
    "md": "m",
    "nfom": "m",
    "obscured": "m",
    "band": "m",
    "ddtt": "ddtt",
    "dpd": "dpd",
    "adt": "adt"
}



def nmr_signal_type_mapping(signal_type_raw):
    """
    映射信号类型到标准化名称
    :param signal_type_raw: 信号类型字符串
    :return: 标准化的信号类型名称
    """
    s = signal_type_raw.lower()
    s = unidecode(s)

    # ——4—— 做一次简单的数字下标、上标转 ascii
    s = re.sub(r"[₀₁₂₃₄₅₆₇₈₉₋₊₌]",
               lambda m: {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
                          "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
                          "₋": "-", "₊": "+", "₌": "="}[m.group()],
               s)
    
    # 如果s在multiplet_dict中，则返回multiplet_dict[s]
    if s in multiplet_dict:
        return multiplet_dict[s]
    else:
        s = "others"
    return s


def parse_signal_content(content):
    """解析括号内的信号内容"""
    content_1 = re.sub(r'(\b[a-zA-Z_]+\b) (\d+H)(?!,)', r'\1,\2', content)
    parts = [p.strip() for p in content_1.split(',')]
    # 基础信息
    signal_type = nmr_signal_type_mapping(parts[0])
    with open(f"signal_stats_{os.getpid()}.tmp", "a") as f:
        f.write(f"{signal_type}\n")
    hydrogen_count = parts[-1]

    # 提取J耦合常数
    j_values = []
    middle_content = " ".join(parts[1:-1])

    for match in J_VALUE_PATTERN.finditer(middle_content):
        values_str, unit = match.groups()
        # 使用正则表达式分割数值
        values = re.split(r'[,\s]+', values_str.strip())
        j_values += [f"{v}{unit}" for v in values if v]

    return signal_type, j_values, hydrogen_count


def parse_nmr_signals(signal_str):
    """主解析函数"""
    results = []

    # 分割各个信号段
    segments = re.findall(r"(\d+\.\d+(?:-\d+\.\d+)?)\s*\(([^)]+)", signal_str)

    for shift_part, content in segments:
        # 解析化学位移
        max_shift, min_shift = parse_shift(shift_part)
        if max_shift is None:
            continue

        # 解析信号内容
        try:
            signal_type, j_values, hydrogen = parse_signal_content(content)
            results.append((
                signal_type,
                j_values,
                hydrogen,
                max_shift,
                min_shift
            ))
        except Exception as e:
            print(f"解析失败：{content} | 错误：{str(e)}")
            continue

    return results




"""
this function maps the NMR solvent to the standard name
"""

def nmr_solvent_mapping(s_solvent):
    """
    解析NMR溶剂信息，返回标准化的溶剂名称
    :param s_solvent:切完了的溶剂
    :return:标准化的溶剂名称
    """
    #用 Unidecode 把所有非 ASCII "长相"字母都转成 ASCII
    #     （这样西里尔 М→M、О→O、С→S 之类都会被替换掉）
    s= s_solvent.lower()
    s = unidecode(s)

    # ——4—— 做一次简单的数字下标、上标转 ascii
    s = re.sub(r"[₀₁₂₃₄₅₆₇₈₉₋₊₌]",
               lambda m: {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
                          "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
                          "₋": "-", "₊": "+", "₌": "="}[m.group()],
               s)

    # ——5—— 规范化映射
    if ":" in s:
        canon = "mixed"
    elif "dmso" in s or "c2d6so" in s or "cd3socd3" in s or "dimethylsulfoxide" in s or "dimethyl sulfoxide" in s or "c2d6os" in s:  # 包含 dms、dmso、DMSO-D6...
        canon = "DMSO-d6"
    elif "cdcl3" in s or "chloroform" in s or "chcl3" in s:  # 包含 CDCl3
        canon = "CDCl3"
    elif "cd3od" in s or "meod" in s or "meoh" in s:  # CD3OD / MeOD
        canon = "CD3OD"
    elif "cd3cn" in s or "acetonitrile" in s or "mecn" in s:  # CD3CN
        canon = "CD3CN"
    elif "methanol" in s:
        canon = "CD3OD"
    elif "cd2cl2" in s or "dichloromethane" in s or "dcm" in s or "methylene chloride" in s:
        canon = "CD2Cl2"
    elif "c6d6" in s or "benzene" in s:
        canon = "C6D6"
    elif "c2d2cl4" in s:
        canon = "C2D2Cl4"
    elif "cd3cocd3" in s or "acetone" in s or "c3d6o" in s or "cd3c(o)cd3" in s or "(CD3)2CO" in s:
        canon = "CD3COCD3"
    elif "d2o" in s or "deuterium oxide" in s:
        canon = "D2O"
    elif "thf" in s:
        canon = "THF-d8"
    elif "dmf" in s:
        canon = "DMF-d7"
    elif "cd3co2d" in s or "cd3coood" in s or "acoh" in s or "acetic acid" in s:
        canon = "CD3CO2D"
    elif "phme" in s or "c6d5cd3" in s or "toluene" in s:
        canon = "PhMe-d8"
    elif "pyridine" in s or "c5d5n" in s:
        canon = "pyridine-d5"
    elif "cf3co2d" in s or "cf3cood" in s or "tfa" in s or "trifluoroacetic acid" in s:
        canon = "CF3CO2D"

    # … 如有更多映射规则，再加 elif
    else:
        canon = "error"
    return canon


def parse_nmr_block(block):
    try:
        nmr_type = NMR_TYPE_REGEX.search(block).group(1).strip()
        nmr_signal = SIGNAL_REGEX.search(block).group(1).strip().replace("\n", " ")

        return (
            nmr_type,
            FREQUENCY_REGEX.search(block).group(1).strip(),
            nmr_solvent_mapping(SOLVENT_REGEX.search(block).group(1).strip()),
            nmr_signal,
            NOTE_REGEX.search(block).group(1).strip().replace("\n", " ") if NOTE_REGEX.search(block) else "")
    except:
        return None


def process_dataframe(df):
    """单线程处理整个DataFrame，带进度条"""
    output_buffer = StringIO()
    writer = csv.writer(output_buffer)
    for i in tqdm(range(0, len(df) - 1, 2), desc="主处理进度"):
        row1 = df.iloc[i]
        row2 = df.iloc[i + 1]
        if row1.category == "paragraph" and row2.category == "molecule":
            row1, row2 = row2, row1
        base_data = [
            row1.filename, row1.smiles,
            row1.hydrogen_count, row1.hydrogen_count_restrict,
            row1.page_in_file, row2.page_in_file,
            row1.location_in_page, row2.location_in_page
        ]
        nmr_records = []
        if pd.notna(row2.smiles):
            blocks = re.split(r"(?=NMR_type:)", str(row2.smiles))
            for block in blocks:
                if record := parse_nmr_block(block):
                    nmr_records.append(record)
        for record in nmr_records:
            writer.writerow([
                *base_data,
                record[0], record[1], record[2], record[3], record[4]
            ])
    output_buffer.seek(0)
    return output_buffer.read()

# --------------- 主执行流程 ----------------
if __name__ == "__main__":
    preprocess_start = time.time()
    df = pd.read_parquet(input_path)
    csv_content = process_dataframe(df)
    with open(output_csv_path, "w") as f:
        header = [
            'filename', 'smiles', 'hydrogen_count', 'hydrogen_count_restrict',
            'page_in_file_smiles', 'page_in_file_para',
            'location_in_page_smiles', 'location_in_page_para',
            'nmr_type', 'nmr_frequency', 'nmr_solvent', 'nmr_shift','nmr_note'
        ]
        f.write(",".join(header) + "\n")
        f.write(csv_content)
    out_parquet = output_path
    pd.read_csv(output_csv_path).to_parquet(out_parquet, index=False)
    # os.remove(output_csv_path)
    print(f"✅ 全部处理完成，总耗时：{time.time() - preprocess_start:.2f}秒")

    # 打印前十行检查
    print("\n==== 结果前十行预览 ====")
    df_out = pd.read_parquet(out_parquet)
    print(df_out.head(10))

    # 修改最终统计结果显示逻辑
    print("\n信号类型统计结果：")
    final_stats = {}
    for fname in os.listdir():
        if fname.startswith("signal_stats_") and fname.endswith(".tmp"):
            with open(fname) as f:
                for line in f:
                    stype = line.strip()
                    final_stats[stype] = final_stats.get(stype, 0) + 1
            os.remove(fname)
    sorted_stats = sorted(final_stats.items(), key=lambda x: x[1], reverse=True)
    for solv, cnt in sorted_stats:
        print(f"{solv}: {cnt}")



'''
now   matched_results_mol_nmr.parquet looks like this
                                             filename                                             smiles  hydrogen_count  hydrogen_count_restrict  page_in_file_smiles  ...  nmr_type nmr_frequency nmr_solvent                                          nmr_shift nmr_note
0         10.1021_ol101792a_NMR_result_processed.json                         C(=O)(OC)C(=O)c1ccc(C)cc1C            12.0                     12.0                    1  ...    1H NMR       400 MHz       CDCl3  2.37 (s, 3H), 2.57 (s, 3H), 3.94 (s, 3H), 7.08...     None
1         10.1021_ol101792a_NMR_result_processed.json                      C(=O)(OCC)C(=O)c1cccc2ccccc12            12.0                     12.0                    2  ...    1H NMR       400 MHz       CDCl3  1.44 (t, J = 7.2 Hz, 3H), 4.49 (q, J = 7.2 Hz,...     None
2         10.1021_ol101792a_NMR_result_processed.json                c1ccc2c(c1)COC(C(=O)OC)(c1ccccc1)C2            16.0                     16.0                    3  ...    1H NMR       400 MHz       CDCl3  3.30 (d, J = 16.3 Hz, 1H), 3.65 (s, 3H), 3.68 ...     None
3         10.1021_ol101792a_NMR_result_processed.json             C(=O)(OCC)C1(c2ccc(OC)cc2)Cc2ccccc2CO1            20.0                     20.0                    3  ...    1H NMR       400 MHz       CDCl3  1.12 (t, J = 7.1 Hz, 3H), 3.31 (d, J = 16.1 Hz...     None
4         10.1021_ol101792a_NMR_result_processed.json       C(F)(F)(F)c1ccc(C2(C(=O)OCC)Cc3ccccc3CO2)cc1            17.0                     17.0                    4  ...    1H NMR       400 MHz       CDCl3  1.11 (t, J = 7.1 Hz, 3H), 3.23 (d, J = 16.0 Hz...     None
..                                                ...                                                ...             ...                      ...                  ...  ...       ...           ...         ...                                                ...      ...
95  10.1021_acs.orglett.5c00003_NMR_result_process...  Cc1ccc(C(=O)CC2CN(c3ccc(C(F)(F)F)cc3)C(=O)C2(C...            22.0                     22.0                   15  ...   13C NMR       101 MHz       CDCl3  197.9, 178.8, 144.6, 142.4, 134.0, 129.5, 128....     None
96  10.1021_acs.orglett.5c00003_NMR_result_process...  Cc1ccc(C(=O)CC2CN(c3ccc(C(F)(F)F)cc3)C(=O)C2(C...            22.0                     22.0                   15  ...   19F NMR       377 MHz       CDCl3                                         -62.07 (s)     None
97  10.1021_acs.orglett.5c00003_NMR_result_process...      Cc1ccc(C(=O)CC2CN(c3ccc(F)cc3)C(=O)C2(C)C)cc1            22.0                     22.0                   15  ...    1H NMR       400 MHz       CDCl3  7.87 (d, J = 8.2 Hz, 2H), 7.58 (dd, J = 9.1, 4...     None
98  10.1021_acs.orglett.5c00003_NMR_result_process...      Cc1ccc(C(=O)CC2CN(c3ccc(F)cc3)C(=O)C2(C)C)cc1            22.0                     22.0                   15  ...   13C NMR       101 MHz       CDCl3             197.9, 178.1, 159.20 (d, J = 243.8 Hz)     None
99  10.1021_acs.orglett.5c00003_NMR_result_process...      Cc1ccc(C(=O)CC2CN(c3ccc(F)cc3)C(=O)C2(C)C)cc1            22.0                     22.0                   15  ...   19F NMR       377 MHz       CDCl3                            -118.02 (d, J = 4.5 Hz)     None
'''



"""
then we need to extract the NMR signals from the text
there will be some patterns to extract the NMR signals
"""


file_path = os.path.join(work_dir, 'matched_results_mol_nmr.parquet')
final_result_parquet = os.path.join(work_dir, 'final_result_0715_1.parquet')
df = pd.read_parquet(file_path)
final_result_filtered_parquet = os.path.join(work_dir, 'final_result_filtered_0715_1.parquet')
final_result_filtered_csv = os.path.join(work_dir, 'final_result_filtered_0715_1.csv')
final_result_filtered_json = os.path.join(work_dir, 'final_result_filtered_0715_1.json')

not_in_multi_dict = []




pattern_shift_range_ptype = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>(?:br\.?\s?[sdtqm]|[^,\s()]+))\s*\)\s*(?:,|$)'
)

pattern_shift_range_ptype_nC = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*(?P<count>\d+)[Cc]\s*\)\s*(?:,|$)'
)

pattern_shift_range_full = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

pattern_multi_J = re.compile(
    r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)   # chemical shift，可以是整数也可以是小数
    \s*
    \(
      \s*
      (?P<ptype>[^,\s()]+)          # multiplet type，比如 d, t, m…
      \s*,\s*
      J\s*=\s*
      (?P<J1>\d+\.\d+)              # 第一个 J 值，必须有小数点
      (?:\s*Hz)?                    # 可选 Hz
      \s*,\s*
      (?P<J2>\d+\.\d+)              # 第二个 J 值，必须有小数点
      \s*Hz
    \)
    \s*
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)

pattern_full_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J[CcPpFf][-,]?[CcPpFf]\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*\)\s*(?:,|$)'
)

pattern_full = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

pattern_full_Hz_nC = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*\d*J(\s?[CcPpFf][-,]?[CcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*,\s*'
    r'(?P<count>\d)C\s*\)\s*(?:,|$)'
)

# 113.9 (d, 2C, C17)
pattern_signal_type_nC_position = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>\d)?C\s*,\s*C(?P<position>\d+)\s*\)\s*(?:,|$)'
)

pattern_full_noHz = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*\)\s*(?:,|$)'
)

pattern_only_j = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*\d*J(\s?[CcPpFf][-,]?[CcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

pattern_full_nC = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<count>\d+)\s?[Cc]\s*\)\s*(?:,|$)'
)


#114.7 (d, J = 23.5 Hz, CH)
pattern_signal_ctye_j_ctype = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*
    (?P<ptype>[^,\s()]+)\s*,\s*
    \d*J(\s?[CcPpFf][-,]?[CcPpFf])?\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*,\s*
    (?P<ctype>
      C
      (?:
        H\d?             # CH, CH2, CH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等
        |=[ONS]          # =O, =N, =S
        |[ONS]           # O, N, S
        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArC[HF]\d?       # ArC, ArCH, ArCH2
      |Ar-C[HF]\d?      # Ar-C, Ar-CH, Ar-CH2
      |BnC[HF]\d?     # BnCH, BnCH2…
      |Bn-C[HF]\d?     # Bn-CH, Bn-CH2…
      |two \s coincidental \s carbons
      |CCl\d?
      |[NOS]?[A-Za-z]*-C(H\d?)?
      |\d?[A-Za-z]+
      |[Cc]+H\d?[ONC]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NC|CN)
      |[ONS](Me|CH\d?)
    )
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)


pattern_C_type = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)
    \s* \( \s*
    (?P<ctype>
      C
      (?:
        H\d?             # CH, CH2, CH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等
        |=[ONS]          # =O, =N, =S
        |[ONS]           # O, N, S
        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArC[HF]\d?       # ArC, ArCH, ArCH2
      |Ar-C[HF]\d?      # Ar-C, Ar-CH, Ar-CH2
      |BnC[HF]\d?     # BnCH, BnCH2…
      |Bn-C[HF]\d?     # Bn-CH, Bn-CH2…
      |two \s coincidental \s carbons
      |(one)? \s* (peak)? \s* merged                           
      |CCl\d?
      |[NOS]?[A-Za-z]*-C(H\d?)?
      |\d?[A-Za-z]+
      |[Cc]+H\d?[ONC]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NC|CN)
      |[ONS](Me|CH\d?)
    )
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)

pattern_C_x_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'C\s*[xX]*\s*\d+|'                # Cx2
        r'C-H\s*[xX]*\s*\d+|'              # C-Hx2
        r'C-Ar\s*[xX]*\s*\d+|'             # C-Arx2
        r'CAr\s*[xX]*\s*\d+|'              # CArx2
        r'CH\s*[xX]*\s*\d+|'               # CHx2
        r'CH2\s*[xX]*\s*\d+|'              # CH2x2
        r'CH3\s*[xX]*\s*\d+'               # CH3x2
    r'))\s*\)\s*(?:,|$)'
)

# 129.0 (2 x CH)
pattern_n_x_C = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'\d+\s*[xX]*\s*C\s*|'
        r'\d+\s*[xX]*\s*C-H\s*|'
        r'\d+\s*[xX]*\s*C-Ar\s*|'
        r'\d+\s*[xX]*\s*CAr\s*|'
        r'\d+\s*[xX]*\s*CH\s*|'
        r'\d+\s*[xX]*\s*CH2\s*|'
        r'\d+\s*[xX]*\s*CH3\s*'
    r'))\s*\)\s*(?:,|$)'
)

pattern_signal_type = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r's\s*|'
        r'd\s*|'
        r't\s*|'
        r'q\s*|'
        r'p\s*|'
        r'hept\s*|'
        r'broad\s*|'
        r'm\s*|'
        r'dd\s*|'
        r'dt\s*|'
        r'td\s*|'
        r'dq\s*|'
        r'qd\s*|'
        r'dp\s*|'
        r'pd\s*|'
        r'tp\s*|'
        r'dquint\s*|'
    r'))\s*\)\s*(?:,|$)'
) 

# example 25.4 (q, C4), 21.9 (s, C3), 18.5 (q, C4'), 18.5 (q, 2C)
pattern_shift_type_nC = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>(?:\d+C|C\d+\'?))\s*\)'
    r'\s*(?:,|$)'
)

# example 122 (2), 200(2)
pattern_shift_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*x*(?P<count>\d+)\s*\)\s*(?:,|$)'
)

pattern_shift = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*(?:,|$)'
)

pattern_handlers_13C = [
        (
            pattern_shift_range_ptype,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],   
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            pattern_shift_range_ptype_nC,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            pattern_shift_range_full,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            pattern_multi_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                [float(m.group('J1')), float(m.group('J2'))]
            )
        ),
        (
            pattern_full_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            pattern_full,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            pattern_full_Hz_nC,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            pattern_signal_type_nC_position,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            pattern_full_noHz,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            pattern_only_j,
            lambda m: (
                float(m.group('shift')),
                None,
                float(m.group('J'))
            )
        ),
        (
            pattern_full_nC,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            pattern_signal_ctye_j_ctype,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            pattern_C_type,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            pattern_C_x_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            pattern_n_x_C,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            pattern_signal_type,
            lambda m: (float(m.group('shift')), m.group('ctype'), None)
        ),
        (
            pattern_shift_type_nC,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            pattern_shift_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            pattern_shift,
            lambda m: (float(m.group('shift')), None, None)
        ),
    ]

def _overlaps(existing, start, end):
    for a, b in existing:
        if start < b and end > a:
            return True
    return False


def parse_line(line: str):
    line = re.sub(r'MHz', 'Hz', line)

    matches = []  # will hold tuples (start, end, result)
    used_spans = []

    # first pass: explicit patterns
    for pat, handler in pattern_handlers_13C:
        for m in pat.finditer(line):
            start, end = m.span()
            if pat in (pattern_full, pattern_full_J) and m.group('ptype') not in multiplet_dict:
                continue
            if _overlaps(used_spans, start, end):
                continue
            matches.append((start, end, handler(m)))
            used_spans.append((start, end))

    # fallback simple shifts
    # mask matched spans
    masked = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        for m in pattern_shift.finditer(s_fb):
            st, ed = m.span()
            # if _overlaps(used_spans, st, ed):
            #     continue
            matches.append((st, ed, (float(m.group('shift')), None, None)))
            used_spans.append((st, ed))

    # sort all matches by original position
    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    # compute final unmatched
    masked_final = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked_final[i] = ' '
    unmatched = re.findall(r'\S+', ''.join(masked_final))

    return results, unmatched

# H
PATTERN_TYPE2 = re.compile(r'''
    # chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Hcount → optional pos
        (?P<type1>[A-Za-z'\s]+)\s*,\s*
        (?:J\s*=\s*(?P<J1>\d+\.\d+)\s*Hz(?:\s*,\s*)?)?
        (?P<count1>\d+(?:\.\d+)?\s*H)
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # B: type → Hcount → [J?] → optional pos
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*H)
        (?:\s*,\s*J\s*=\s*(?P<J2>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # C: Hcount → type → [J?] → optional pos
        (?P<count3>\d+(?:\.\d+)?\s*H)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*(?P<J3>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)


PATTERN_TYPE1 = re.compile(
    r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Hcount
        (?P<type1>[A-Za-z'\s]+)\s*,\s*
        (?:J\s*=\s*(?P<J1>\d+\.\d+)\s*Hz(?:\s*,\s*)?)?
        (?P<count1>\d+(?:\.\d+)?\s*H)

      |
        # B: type → Hcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*H)
        (?:\s*,\s*J\s*=\s*(?P<J2>\d+\.\d+)\s*Hz)?

      |
        # C: Hcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*H)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*(?P<J3>\d+\.\d+)\s*Hz)?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)


PATTERN_MULTY_J1 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Hcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J1>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*H)

      |
        # B: type → Hcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*H)
        (?:\s*,\s*J\s*=\s*
            (?P<J2>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # C: Hcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*H)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*
            (?P<J3>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)            

PATTERN_NMR_MULTIJ2 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        -?\d+\.\d+(?:\s*-\s*-?\d+\.\d+)?      # e.g. -0.12 或 7.13-7.03
    )\s*
    \(\s*
    (?:
        # A: type → J-list → Hcount
        (?P<type1>[A-Za-z'\s]+)
        \s*,\s*
        (?P<J1>
            # 第一个 J=...
            J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
            # 后面可以跟若干 “, J=? 数字[Hz]”
            (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
        )
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*H)

      |
        # B: type → Hcount → J-list
        (?P<type2>[A-Za-z'\s]+)
        \s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*H)
        (?:\s*,\s*
            (?P<J2>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?

      |
        # C: Hcount → type → J-list
        (?P<count3>\d+(?:\.\d+)?\s*H)
        \s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*
            (?P<J3>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

# # 预编译正则表达式：J值
# J_VALUE_PATTERN = re.compile(
#     r"J\s*=\s*((?:\d+\.?\d*[\s,]+)*\d+\.?\d*)\s*([a-zA-Z]+)",
#     re.IGNORECASE
# )


SHIFT_PATTERN = re.compile(
    r'(-?\d+\.\d+)(?:\s*-\s*(-?\d+\.\d+))?'
)


def parse_shift(shift_str):
    """解析化学位移范围（修复版）"""
    match = SHIFT_PATTERN.search(shift_str)
    if not match:
        return (None, None)

    # 提取基础值
    first_val = float(match.group(1))
    second_val = float(match.group(2)) if match.group(2) else None

    # 处理范围逻辑
    if second_val is not None:
        min_shift = min(first_val, second_val)
        max_shift = max(first_val, second_val)
    else:
        min_shift = max_shift = first_val

    # 保留两位小数并返回正确顺序
    return (round(max_shift, 2), round(min_shift, 2))  # (max, min)



def parse_hydrogen(hydrogen_str):
    """解析氢数"""
    if hydrogen_str:
        match = re.search(r"(\d+(?:\.\d+)?)\s*[H]\b", hydrogen_str)
        if match:
            number = float(match.group(1))
            # 判断是不是整数
            if number.is_integer():
                return f"{int(number)}H"
            else:
                return f"{number}H"
    return None




def is_valid_format(s):
    pattern = r'^\s*(\d[^\()]*\))(\s*,\s*\d[^\()]*\))*\s*,?$'
    return bool(re.match(pattern, s))

def parse_nmr_signals_H(signal_str: str):
    signal_str = re.sub(r';', ',', signal_str)
    # 如果line是", 13"结尾的，则去掉
    if signal_str.endswith(', 13'):
        signal_str = signal_str[:-4]
    
    signal_str = re.sub(r'，', ',', signal_str)
    signal_str = re.sub(r'≈', '=', signal_str)
    
    signal_str = re.sub(r'\)\s,', '),', signal_str)
    signal_str = re.sub(r'JHH', 'J', signal_str)
    signal_str = re.sub(r'JPH', 'J', signal_str)
    signal_str = re.sub(r'JP-H', 'J', signal_str)
    signal_str = re.sub(r'JFH', 'J', signal_str)
    signal_str = re.sub(r'JF-H', 'J', signal_str)
    signal_str = re.sub(r'JAB', 'J', signal_str)
    signal_str = re.sub(r'JBA', 'J', signal_str)
    signal_str = re.sub(r'JH-H', 'J', signal_str)
    signal_str = re.sub(r'\bJ\d+\b', 'J', signal_str)
    signal_str = re.sub(r'\b\d+J\b', 'J', signal_str)
    signal_str = re.sub(r'\bJ\s[123]', 'J', signal_str)
    signal_str = re.sub(r'[\x00-\x1F]', '', signal_str)
    # 清除 br. s/d/t/q -> brs/brd/brt/brq
    signal_str = re.sub(r'br\.\s*([sdtq])\.*', r'br \1', signal_str)
    signal_str = re.sub(r'app\.\s*([sdtq])\.*', r'app \1', signal_str)
    signal_str = re.sub(r'virt\.\s*([sdtq])\.*', r'app \1', signal_str)
    # 替换 br, s/d/t/q -> br s/br d 等（保留空格）
    signal_str = re.sub(r'br,\s*([sdtq])\.*', r'br \1', signal_str)
    signal_str = re.sub(r'([sdtq])\.\s*br\.*', r'br \1', signal_str)
    signal_str = re.sub(r'([sdtq]),\s*br\.*', r'br \1', signal_str)
    signal_str = re.sub(r'\(\s*(s|m)\s+(\d+H)\s*\)', r'(\1, \2)', signal_str)
    signal_str = re.sub(r'\s*and\b', ',', signal_str)
    signal_str = re.sub(r'\s*&\b', ',', signal_str)
    signal_str = re.sub(r',\s*(H-?\d+|CArH|CarH|CH=|CHAr|CHar|CH-aromatic|OH|CHarom|Har|Ar-H|aromatic\sH|NH|ArH|CH2|CH3|CH|Ph|PhH|PhCH2|HAr|Ha|Hb|Hc|Hd|He|Hf|Hg|Hh|Hi|Hj|Hk|Hl|Hm|Hn|Ho|Hp|Hq|Hr|Hs)\s*\)', ')', signal_str)

   
    matches = []
    used_spans = []

    patterns = [
        (PATTERN_TYPE1, 'type1'),
        (PATTERN_TYPE2, 'type2'),
        (PATTERN_MULTY_J1, 'multyj1'),
        (PATTERN_NMR_MULTIJ2, 'multyj2'),
    ]

    for pat, _ in patterns:
        for m in pat.finditer(signal_str):
            start, end = m.span()
            if _overlaps(used_spans, start, end):
                continue
            shift_part = m.group('shift')
            max_shift, min_shift = parse_shift(shift_part)
            gd = m.groupdict()
            mnemonic = next((gd[k].strip() for k in ('type1','type2','type3') if gd.get(k)), None)
            j_str = next((gd[k] for k in ('J1','J2','J3') if gd.get(k)), None)
            hydrogen = next((gd[k] for k in ('count1','count2','count3') if gd.get(k)), None)
            j_values = []
            if j_str:
                js = re.sub(r'Hz', '', j_str)
                j_values = [f"{v.strip()}Hz" for v in js.split(',') if v.strip()]
            h_count = parse_hydrogen(hydrogen)
            res = (multiplet_dict.get(mnemonic), j_values, h_count, max_shift, min_shift)
            matches.append((start, end, res))
            used_spans.append((start, end))

    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    masked = list(signal_str)
    for start, end, _ in matches:
        for i in range(start, end): masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        while True:
            m = pattern_shift.search(s_fb)
            if not m: break
            st, ed = m.span()
            if _overlaps(used_spans, st, ed):
                s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
                continue
            results.append((float(m.group('shift')), None, None))
            used_spans.append((st, ed))
            s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
        leftover = s_fb

    unmatched = re.findall(r'\S+', leftover)

    if is_valid_format(' '.join(unmatched)):
        unmatched = ""

    return results, unmatched



# F

F_pattern_shift_range_ptype = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>(?:br\.?\s?[sdtqm]|[^,\s()]+))\s*\)\s*(?:,|$)'
)

F_pattern_shift_range_ptype_nF = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*(?P<count>\d+)[Fc]\s*\)\s*(?:,|$)'
)

F_pattern_shift_range_full = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

F_pattern_multi_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*'
    r'(?P<J1>\d+(?:\.\d+)?)\s*(Hz)*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

# JFF等
F_pattern_full_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J[FcPpFf][-,]?[FcPpFf]\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*\)\s*(?:,|$)'
)

F_pattern_full = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

F_pattern_full_Hz_nF = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*,\s*'
    r'(?P<count>\d)F\s*\)\s*(?:,|$)'
)

# 119.9 (d, 2F, F17)
F_pattern_signal_type_nF_position = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>\d)?F\s*,\s*F(?P<position>\d+)\s*\)\s*(?:,|$)'
)

F_pattern_full_noHz = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*\)\s*(?:,|$)'
)

F_pattern_only_j = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

F_pattern_full_nF = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<count>\d+)\s?[Fc]\s*\)\s*(?:,|$)'
)


#114.7 (d, J = 23.5 Hz, FH)
F_pattern_signal_ctye_j_ctype = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*
    (?P<ptype>[^,\s()]+)\s*,\s*
    \d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*,\s*
    (?P<ctype>
      F
      (?:
        H\d?             # FH, FH2, FH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等

        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArF(?:H\d?)?     # ArF, ArFH, ArFH2
      |Ar-F(?:H\d?)?    # Ar-F, Ar-FH, Ar-FH2
      |BnF(?:H\d?)?     # BnF, BnFH, BnFH2
      |Bn-F(?:H\d?)?    # Bn-F, Bn-FH, Bn-FH2
      |two \s coincidental \s carbons
      |FFl\d?
      |[NOS]?[A-Za-z]*-F(H\d?)?
      |\d?[A-Za-z]+
      |[Fc]+H\d?[ONF]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NF|FN)
      |[ONS](Me|FH\d?)
      |[BC]F\d*        # BF2, CF3, etc.
    )
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)


F_pattern_F_type = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)
    \s* \( \s*
    (?P<ctype>
      F
      (?:
        H\d?             # FH, FH2, FH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等
        |=[ONS]          # =O, =N, =S
        |[ONS]           # O, N, S
        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArF(?:H\d?)?     # ArF, ArFH, ArFH2
      |Ar-F(?:H\d?)?    # Ar-F, Ar-FH, Ar-FH2
      |BnF(?:H\d?)?     # BnF, BnFH, BnFH2
      |Bn-F(?:H\d?)?    # Bn-F, Bn-FH, Bn-FH2
      |two \s coincidental \s carbons
      |(one)? \s* (peak)? \s* merged                           
      |FFl\d?
      |[NOS]?[A-Za-z]*-F(H\d?)?
      |\d?[A-Za-z]+
      |[Fc]+H\d?[ONF]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NF|FN)
      |[ONS](Me|FH\d?)
      |[BC]F\d*   # BF2, CF3, etc.
    )
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)

F_pattern_F_x_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'F\s*[xX]*\s*\d+|'                # Fx2
        r'F-H\s*[xX]*\s*\d+|'              # F-Hx2
        r'F-Ar\s*[xX]*\s*\d+|'             # F-Arx2
        r'FAr\s*[xX]*\s*\d+|'              # FArx2
        r'FH\s*[xX]*\s*\d+|'               # FHx2
        r'FH2\s*[xX]*\s*\d+|'              # FH2x2
        r'FH3\s*[xX]*\s*\d+'               # FH3x2
    r'))\s*\)\s*(?:,|$)'
)

# 129.0 (2 x FH)
F_pattern_n_x_F = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'\d+\s*[xX]*\s*F\s*|'
        r'\d+\s*[xX]*\s*F-H\s*|'
        r'\d+\s*[xX]*\s*F-Ar\s*|'
        r'\d+\s*[xX]*\s*FAr\s*|'
        r'\d+\s*[xX]*\s*FH\s*|'
        r'\d+\s*[xX]*\s*FH2\s*|'
        r'\d+\s*[xX]*\s*FH3\s*'
    r'))\s*\)\s*(?:,|$)'
)

F_pattern_signal_type = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r's\s*|'
        r'd\s*|'
        r't\s*|'
        r'q\s*|'
        r'p\s*|'
        r'hept\s*|'
        r'broad\s*|'
        r'm\s*|'
        r'dd\s*|'
        r'dt\s*|'
        r'td\s*|'
        r'dq\s*|'
        r'qd\s*|'
        r'dp\s*|'
        r'pd\s*|'
        r'tp\s*|'
        r'dquint\s*|'
    r'))\s*\)\s*(?:,|$)'
) 

# example 25.4 (q, F4), 21.9 (s, F3), 18.5 (q, F4'), 18.5 (q, 2F)
F_pattern_shift_type_nF = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>(?:\d+F|F|F\d+\'?))\s*\)'
    r'\s*(?:,|$)'
)

# example 122 (2), 200(2)
F_pattern_shift_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*x*(?P<count>\d+)\s*\)\s*(?:,|$)'
)

F_pattern_shift = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*(?:,|$)'
)

F_pattern_full_J_2 = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 d, tt, AB…
      \s*,\s*
      J[A-Za-z]*\s*=\s*(?P<J>\d+(?:\.\d+)?)  # JHF、JAB 等
      \s*Hz
    \s*\)
''', re.VERBOSE)

# 匹配 -145 (dd, J = 56.6, 28.3 Hz, 2F, BF2) 这种格式
F_pattern_multi_J_with_F_count_and_ctype = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 dd
      \s*,\s*
      J\s*=\s*(?P<J1>\d+(?:\.\d+)?)\s*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz  # J = 56.6, 28.3 Hz
      \s*,\s*
      (?P<count>\d+F)              # 2F
      \s*,\s*
      (?P<ctype>[A-Za-z\d]+)         # 任意字母组合，如 BF2, CF3, ArF, etc.
    \s*\)
''', re.VERBOSE)

# 像氢谱的

F_PATTERN_TYPE2 = re.compile(r'''
    # chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount → optional pos
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*    # 可选2JFF\JFP\JF、J  etc。
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*F)
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # B: type → Fcount → [J?] → optional pos.可选J(FF)等
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*F)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # C: Fcount → type → [J?] → optional pos
        (?P<count3>\d+(?:\.\d+)?\s*F)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

F_PATTERN_TYPE1 = re.compile(
    r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*F)

      |
        # B: type → Fcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*F)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?

      |
        # C: Fcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*F)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)

F_PATTERN_MULTY_J1 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J1>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*F)

      |
        # B: type → Fcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*F)
        (?:\s*,\s*J\s*=\s*
            (?P<J2>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # C: Fcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*F)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*
            (?P<J3>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # D: type → [J?] (no F count)
        (?P<type4>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J4>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)         
    
F_PATTERN_NMR_MULTIJ2 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        -?\d+\.\d+(?:\s*-\s*-?\d+\.\d+)?      # e.g. -0.12 或 7.13-7.03
    )\s*
    \(\s*
    (?:
        # A: type → J-list → Fcount
        (?P<type1>[A-Za-z'\s]+)
        \s*,\s*
        (?P<J1>
            # 第一个 J=...
            J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
            # 后面可以跟若干 “, J=? 数字[Hz]”
            (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
        )
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*F)

      |
        # B: type → Hcount → J-list
        (?P<type2>[A-Za-z'\s]+)
        \s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*F)
        (?:\s*,\s*
            (?P<J2>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?

      |
        # C: Fcount → type → J-list
        (?P<count3>\d+(?:\.\d+)?\s*F)
        \s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*
            (?P<J3>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

F_pattern_handlers_19F = [
        (
            F_pattern_shift_range_ptype,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],   
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            F_pattern_shift_range_ptype_nF,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            F_pattern_shift_range_full,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            F_pattern_multi_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                [float(m.group('J1')), float(m.group('J2'))]
            )
        ),
        (
            F_pattern_full_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            F_pattern_full,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            F_pattern_full_Hz_nF,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            F_pattern_signal_type_nF_position,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            F_pattern_full_noHz,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            F_pattern_only_j,
            lambda m: (
                float(m.group('shift')),
                None,
                float(m.group('J'))
            )
        ),
        (
            F_pattern_full_nF,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            F_pattern_signal_ctye_j_ctype,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            F_pattern_F_type,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            F_pattern_F_x_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            F_pattern_n_x_F,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            F_pattern_signal_type,
            lambda m: (float(m.group('shift')), m.group('ctype'), None)
        ),
        (
            F_pattern_shift_type_nF,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            F_pattern_shift_number,
            lambda m: (float(m.group('shift')), None, None)
        ),       
        (
            F_pattern_full_J_2,
            lambda m: (float(m.group('shift')), m.group('ptype'), float(m.group('J')))
        ),
        (
            F_pattern_multi_J_with_F_count_and_ctype,
            lambda m: (float(m.group('shift')), m.group('ptype'), [float(m.group('J1')), float(m.group('J2'))])
        ),
    ]



def _overlaps(existing, start, end):
    for a, b in existing:
        if start < b and end > a:
            return True
    return False


SHIFT_PATTERN = re.compile(
    r'(-?\d+\.\d+)(?:\s*-\s*(-?\d+\.\d+))?'
)

def parse_shift_F(shift_str):
    """解析化学位移范围（修复版）"""

    match = SHIFT_PATTERN.search(shift_str)
    if not match:
        return (None, None)

    # 提取基础值
    first_val = float(match.group(1))
    second_val = float(match.group(2)) if match.group(2) else None

    # 处理范围逻辑
    if second_val is not None:
        min_shift = min(first_val, second_val)
        max_shift = max(first_val, second_val)
    else:
        min_shift = max_shift = first_val

    # 保留两位小数并返回正确顺序
    return (round(max_shift, 2), round(min_shift, 2))  # (max, min)


def parse_line_19F(line: str):
    line = re.sub(r'MHz', 'Hz', line)
    line = re.sub(r'\(CF3\)', '', line)
    line = re.sub(r', CF3', '', line)

    if line.endswith(' 13'):
        line = re.sub(r'\s*13$', '', line)

    matches = []  # will hold tuples (start, end, result)
    used_spans = []
    results = []
    # first pass: explicit patterns
    for pat, handler in F_pattern_handlers_19F:
        for m in pat.finditer(line):
            start, end = m.span()
            if pat in (F_pattern_full, F_pattern_full_J) and m.group('ptype') not in multiplet_dict:
                continue
            if _overlaps(used_spans, start, end):
                continue
            matches.append((start, end, handler(m)))
            used_spans.append((start, end))

    # fallback simple shifts
    # mask matched spans
    masked = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        for m in F_pattern_shift.finditer(s_fb):
            st, ed = m.span()
            # if _overlaps(used_spans, st, ed):
            #     continue
            matches.append((st, ed, (float(m.group('shift')), None, None)))
            used_spans.append((st, ed))


    # sort all matches by original position
    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    # compute final unmatched
    masked_final = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked_final[i] = ' '
    unmatched = re.findall(r'\S+', ''.join(masked_final))

    results_2 = []
    used_spans_2 = []

    if len(unmatched) > 0:
        new_matches = []

        # unmatched 组合成新的 newline
        new_line = ' '.join(unmatched)
        # print(f"new_line: {new_line}")
        patterns = [
            (F_PATTERN_TYPE1, 'type1'),
            (F_PATTERN_TYPE2, 'type2'),
            (F_PATTERN_MULTY_J1, 'multyj1'),
            (F_PATTERN_NMR_MULTIJ2, 'multyj2'),
        ]

        for pat, _ in patterns:
            for m in pat.finditer(new_line):
                start, end = m.span()
                if _overlaps(used_spans_2, start, end):
                    continue
                shift_part = m.group('shift')
                max_shift, min_shift = parse_shift_F(shift_part)
                gd = m.groupdict()
                mnemonic = next((gd[k].strip() for k in ('type1','type2','type3','type4') if gd.get(k)), None)
                j_str = next((gd[k] for k in ('J1','J2','J3','J4') if gd.get(k)), None)
                j_values = []
                if j_str:
                    js = re.sub(r'Hz', '', j_str)
                    j_values = [f"{v.strip()}Hz" for v in js.split(',') if v.strip()]
                new_matches.append((start, end, ([max_shift, min_shift], multiplet_dict.get(mnemonic), j_values)))
                used_spans_2.append((start, end))

        new_matches.sort(key=lambda x: x[0])
        results_2 = [res for _, _, res in new_matches]
        # print(f"results_2: {results_2}")
        masked = list(new_line)
        for start_matches, end_matches, _ in new_matches:
            start, end = start_matches, end_matches
            start = int(start)
            end = int(end)
            for i in range(start, end): masked[i] = ' '
        leftover = ''.join(masked)

        if re.fullmatch(r'[\d\.,\s\-]*', leftover):
            s_fb = leftover
            while True:
                m = F_pattern_shift.search(s_fb)
                if not m: break
                st, ed = m.span()
                if _overlaps(used_spans_2, st, ed):
                    s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
                    continue
                used_spans_2.append((st, ed))
                s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
            leftover = s_fb

        unmatched = re.findall(r'\S+', leftover)

    # 合并results_2和results
    results_all = results + results_2

    return results_all, unmatched


P_pattern_shift_range_ptype = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>(?:br\.?\s?[sdtqm]|[^,\s()]+))\s*\)\s*(?:,|$)'
)

P_pattern_shift_range_ptype_nP = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*(?P<count>\d+)[Pc]\s*\)\s*(?:,|$)'
)

P_pattern_shift_range_full = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

P_pattern_multi_J = re.compile( 
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*'
    r'(?P<J1>\d+(?:\.\d+)?)\s*(Hz)*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

# JFF等
P_pattern_full_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J[FcPpFf][-,]?[FcPpFf]\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*\)\s*(?:,|$)'
)

P_pattern_full = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

P_pattern_full_Hz_nP = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*,\s*'
    r'(?P<count>\d)P\s*\)\s*(?:,|$)'
)

# 119.9 (d, 2P, P17)
P_pattern_signal_type_nP_position = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>\d)?P\s*,\s*P(?P<position>\d+)\s*\)\s*(?:,|$)'
)

P_pattern_full_noHz = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*\)\s*(?:,|$)'
)

P_pattern_only_j = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

P_pattern_full_nP = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<count>\d+)\s?[Pp]\s*\)\s*(?:,|$)'
)


P_pattern_P_x_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'P\s*[xX]*\s*\d+|'                # Fx2
        r'P\s*[xX]*\s*\d+|'              # F-Hx2
        r'P-Ar\s*[xX]*\s*\d+|'             # F-Arx2
        r'PAr\s*[xX]*\s*\d+|'              # FArx2
        r'PH\s*[xX]*\s*\d+|'               # FHx2
        r'PH2\s*[xX]*\s*\d+|'              # FH2x2
        r'PH3\s*[xX]*\s*\d+'               # FH3x2
    r'))\s*\)\s*(?:,|$)'
)

# 129.0 (2 x FH)
P_pattern_n_x_P = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'\d+\s*[xX]*\s*P\s*|'
        r'\d+\s*[xX]*\s*P-H\s*|'
        r'\d+\s*[xX]*\s*P-Ar\s*|'
        r'\d+\s*[xX]*\s*PAr\s*|'
            r'\d+\s*[xX]*\s*PH\s*|'
        r'\d+\s*[xX]*\s*PH2\s*|'
        r'\d+\s*[xX]*\s*PH3\s*'
    r'))\s*\)\s*(?:,|$)'
)

P_pattern_signal_type = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r's\s*|'
        r'd\s*|'
        r't\s*|'
        r'q\s*|'
        r'p\s*|'
        r'hept\s*|'
        r'broad\s*|'
        r'm\s*|'
        r'dd\s*|'
        r'dt\s*|'
        r'td\s*|'
        r'dq\s*|'
        r'qd\s*|'
        r'dp\s*|'
        r'pd\s*|'
        r'tp\s*|'
        r'dquint\s*|'
    r'))\s*\)\s*(?:,|$)'
) 

# example 25.4 (q, P4), 21.9 (s, P3), 18.5 (q, P4'), 18.5 (q, 2P)
P_pattern_shift_type_nP = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>(?:\d+P|P|P\d+\'?))\s*\)'
    r'\s*(?:,|$)'
)

# example 122 (2), 200(2)
P_pattern_shift_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*x*(?P<count>\d+)\s*\)\s*(?:,|$)'
)

P_pattern_shift = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*(?:,|$)'
)


P_pattern_full_J_2 = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 d, tt, AB…
      \s*,\s*
      J[A-Za-z]*\s*=\s*(?P<J>\d+(?:\.\d+)?)  # JHF、JAB 等
      \s*Hz
    \s*\)
''', re.VERBOSE)


# 像氢谱的

P_PATTERN_TYPE2 = re.compile(r'''
    # chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Pcount → optional pos
        (?P<type1>[A-Za-z'\s]+)\s*
        # (?:J\s*=\s*(?P<J1>\d+\.\d+)\s*Hz(?:\s*,\s*)?)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*    # 可选2JFF\JFP\JF、J  etc。
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*P)
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # B: type → Pcount → [J?] → optional pos.可选J(FF)等
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*P)
        # (?:\s*,\s*J\s*=\s*(?P<J2>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # C: Pcount → type → [J?] → optional pos
        (?P<count3>\d+(?:\.\d+)?\s*P)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        # (?:\s*,\s*J\s*=\s*(?P<J3>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)


P_PATTERN_TYPE1 = re.compile(
    r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Pcount
        (?P<type1>[A-Za-z'\s]+)\s*
        # (?:J\s*=\s*(?P<J1>\d+\.\d+)\s*Hz(?:\s*,\s*)?)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*P)

      |
        # B: type → Pcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*P)
        # (?:\s*,\s*J\s*=\s*(?P<J2>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?

      |
        # C: Pcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*P)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        # (?:\s*,\s*J\s*=\s*(?P<J3>\d+\.\d+)\s*Hz)?
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)


P_PATTERN_MULTY_J1 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Pcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J1>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*P)

      |
        # B: type → Pcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*P)
        (?:\s*,\s*J\s*=\s*
            (?P<J2>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # C: Pcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*P)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*
            (?P<J3>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # D: type → [J?] (no P count)
        (?P<type4>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J4>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)            

P_PATTERN_NMR_MULTIJ2 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        -?\d+\.\d+(?:\s*-\s*-?\d+\.\d+)?      # e.g. -0.12 或 7.13-7.03
    )\s*
    \(\s*
    (?:
        # A: type → J-list → Pcount
        (?P<type1>[A-Za-z'\s]+)
        \s*,\s*
        (?P<J1>
            # 第一个 J=...
            J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
            # 后面可以跟若干 “, J=? 数字[Hz]”
            (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
        )
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*P)

      |
        # B: type → Pcount → J-list
        (?P<type2>[A-Za-z'\s]+)
        \s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*P)
        (?:\s*,\s*
            (?P<J2>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?

      |
        # C: Pcount → type → J-list
        (?P<count3>\d+(?:\.\d+)?\s*P)
        \s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*
            (?P<J3>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

P_pattern_handlers_31P = [
        (
            P_pattern_shift_range_ptype,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],   
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            P_pattern_shift_range_ptype_nP,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            P_pattern_shift_range_full,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            P_pattern_multi_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                [float(m.group('J1')), float(m.group('J2'))]
            )
        ),
        (
            P_pattern_full_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            P_pattern_full,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            P_pattern_full_Hz_nP,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            P_pattern_signal_type_nP_position,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            P_pattern_full_noHz,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            P_pattern_only_j,
            lambda m: (
                float(m.group('shift')),
                None,
                float(m.group('J'))
            )
        ),
        (
            P_pattern_full_nP,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            P_pattern_P_x_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            P_pattern_n_x_P,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            P_pattern_signal_type,
            lambda m: (float(m.group('shift')), m.group('ctype'), None)
        ),
        (
            P_pattern_shift_type_nP,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            P_pattern_shift_number,
            lambda m: (float(m.group('shift')), None, None)
        ),       
        (
            P_pattern_full_J_2,
            lambda m: (float(m.group('shift')), m.group('ptype'), float(m.group('J')))
        ),
    ]

def parse_shift_P(shift_str):
    """解析化学位移范围（修复版）"""

    match = SHIFT_PATTERN.search(shift_str)
    if not match:
        return (None, None)

    # 提取基础值
    first_val = float(match.group(1))
    second_val = float(match.group(2)) if match.group(2) else None

    # 处理范围逻辑
    if second_val is not None:
        min_shift = min(first_val, second_val)
        max_shift = max(first_val, second_val)
    else:
        min_shift = max_shift = first_val

    # 保留两位小数并返回正确顺序
    return (round(max_shift, 2), round(min_shift, 2))  # (max, min)


def parse_line_31P(line: str):
    line = re.sub(r'MHz', 'Hz', line)
    # line = re.sub(r'\(CF3\)', '', line)
    # line = re.sub(r', CF3', '', line)

    if line.endswith(' 13'):
        line = re.sub(r'\s*13$', '', line)

    matches = []  # will hold tuples (start, end, result)
    used_spans = []
    results = []
    # first pass: explicit patterns
    for pat, handler in P_pattern_handlers_31P:
        for m in pat.finditer(line):
            start, end = m.span()
            if pat in (P_pattern_full, P_pattern_full_J) and m.group('ptype') not in multiplet_dict:
                if multiplet_dict.get(m.group('ptype')) is None:
                    not_in_multi_dict.append(m.group('ptype'))
                continue
            if _overlaps(used_spans, start, end):
                continue
            matches.append((start, end, handler(m)))
            used_spans.append((start, end))

    # fallback simple shifts
    # mask matched spans
    masked = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        for m in P_pattern_shift.finditer(s_fb):
            st, ed = m.span()
            # if _overlaps(used_spans, st, ed):
            #     continue
            matches.append((st, ed, (float(m.group('shift')), None, None)))
            used_spans.append((st, ed))


    # sort all matches by original position
    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    # compute final unmatched
    masked_final = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked_final[i] = ' '
    unmatched = re.findall(r'\S+', ''.join(masked_final))

    results_2 = []
    used_spans_2 = []

    if len(unmatched) > 0:
        new_matches = []

        # unmatched 组合成新的 newline
        new_line = ' '.join(unmatched)
        # print(f"new_line: {new_line}")
        patterns = [
            (P_PATTERN_TYPE1, 'type1'),
            (P_PATTERN_TYPE2, 'type2'),
            (P_PATTERN_MULTY_J1, 'multyj1'),
            (P_PATTERN_NMR_MULTIJ2, 'multyj2'),
        ]

        for pat, _ in patterns:
            for m in pat.finditer(new_line):
                start, end = m.span()
                if _overlaps(used_spans_2, start, end):
                    continue
                shift_part = m.group('shift')
                max_shift, min_shift = parse_shift_P(shift_part)
                gd = m.groupdict()
                mnemonic = next((gd[k].strip() for k in ('type1','type2','type3','type4') if gd.get(k)), None)
                j_str = next((gd[k] for k in ('J1','J2','J3','J4') if gd.get(k)), None)
                j_values = []
                if j_str:
                    js = re.sub(r'Hz', '', j_str)
                    j_values = [f"{v.strip()}Hz" for v in js.split(',') if v.strip()]
                if multiplet_dict.get(mnemonic) is None:
                    not_in_multi_dict.append(mnemonic)
                new_matches.append((start, end, ([max_shift, min_shift], multiplet_dict.get(mnemonic), j_values)))
                used_spans_2.append((start, end))

        new_matches.sort(key=lambda x: x[0])
        results_2 = [res for _, _, res in new_matches]
        # print(f"results_2: {results_2}")
        masked = list(new_line)
        for start_matches, end_matches, _ in new_matches:
            start, end = start_matches, end_matches
            start = int(start)
            end = int(end)
            for i in range(start, end): masked[i] = ' '
        leftover = ''.join(masked)

        if re.fullmatch(r'[\d\.,\s\-]*', leftover):
            s_fb = leftover
            while True:
                m = P_pattern_shift.search(s_fb)
                if not m: break
                st, ed = m.span()
                if _overlaps(used_spans_2, st, ed):
                    s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
                    continue
                used_spans_2.append((st, ed))
                s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
            leftover = s_fb

        unmatched = re.findall(r'\S+', leftover)

    # 合并results_2和results
    results_all = results + results_2

    return results_all, unmatched


# # 顶层逗号拆分（忽略括号内逗号）
# _SPLIT_RE = re.compile(r',\s*(?![^(]*\))')

# _SIGNAL_RE = re.compile(
#     r'^\s*'
#     r'(?P<shift>-?\d+(?:\.\d+)?(?:\s*-\s*-?\d+(?:\.\d+)?)?)'     # 支持shift 或 shift-shift，允许降序，高到低
#     r'\s*'
#     r'(?:'
#       r'\('
#         r'\s*(?P<ptype>[^{}\)]+?)\s*'                             # 峰型
#         r'(?P<js>(?:\{\s*\d+(?:\.\d+)?\s*(?:Hz)\s*\})+)'              # {J Hz}块
#       r'\)'
#     r')?'
#     r'\s*$'
# )
B_pattern_shift_range_ptype = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>(?:br\.?\s?[sdtqm]|[^,\s()]+))\s*\)\s*(?:,|$)'
)

B_pattern_shift_range_ptype_nB = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*(?P<count>\d+)[Bc]\s*\)\s*(?:,|$)'
)

B_pattern_shift_range_full = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

B_pattern_multi_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*'
    r'(?P<J1>\d+(?:\.\d+)?)\s*(Hz)*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

# JFF等
B_pattern_full_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J[BcPpBpBf][-,]?[BcPpBpBf]\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*\)\s*(?:,|$)'
)

B_pattern_full = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

B_pattern_full_Hz_nB = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*\d*J(\s?[BcPpBpBf][-,]?[BcPpBpBf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*,\s*'
    r'(?P<count>\d)B\s*\)\s*(?:,|$)'
)

# 119.9 (d, 2F, F17)
B_pattern_signal_type_nB_position = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>\d)?B\s*,\s*B(?P<position>\d+)\s*\)\s*(?:,|$)'
)

B_pattern_full_noHz = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*\)\s*(?:,|$)'
)

B_pattern_only_j = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*\d*J(\s?[BbPpHhpFf][-,]?[BbPpHhFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

B_pattern_full_nB = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<count>\d+)\s?[Bb]\s*\)\s*(?:,|$)'
)

B_pattern_signal_ctye_j_ctype = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*
    (?P<ptype>[^,\s()]+)\s*,\s*
    (?:\d*)?J[A-Za-z\-]*\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*
    (?:,\s*(?P<ctype>
      B
      (?:
        H\d?             # FH, FH2, FH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等

        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArB(?:H\d?)?     # ArB, ArBH, ArBH2
      |Ar-B(?:H\d?)?    # Ar-B, Ar-BH, Ar-BH2
      |BnB(?:H\d?)?     # BnB, BnBH, BnBH2
      |Bn-B(?:H\d?)?    # Bn-B, Bn-BH, Bn-BH2
      |two \s coincidental \s carbons
      |BBfl\d?
      |[NOS]?[A-Za-z]*-B(H\d?)?
      |\d?[A-Za-z]+
      |[Bc]+H\d?[ONB]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NB|BN)
      |[ONS](Me|BH\d?)
    ))?
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)


B_pattern_B_type = re.compile(r'''
    (?P<shift>\s*-?\d+(?:\.\d+)?)
    \s* \( \s*
    (?P<ctype>
      B
      (?:
        H\d?             # FH, FH2, FH3
        (?:-[A-Za-z]+\d?)?  # 可选地再接 -Ph, -X2 等
        |=[ONS]          # =O, =N, =S
        |[ONS]           # O, N, S
        |-[0-9]+'?       # -1, -2'
        |-[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |-\d+[A-Za-z]+\d?   # -1Glu2   
        |[0-9]+'?       # -1, -2'
        |[A-Za-z]+\d?   # -Ph, -X2, -R3…
        |\d+[A-Za-z]+\d?   # -1Glu2   
      )?
      |ArB(?:H\d?)?     # ArB, ArBH, ArBH2
      |Ar-B(?:H\d?)?    # Ar-B, Ar-BH, Ar-BH2
      |BnB(?:H\d?)?     # BnB, BnBH, BnBH2
      |Bn-B(?:H\d?)?    # Bn-B, Bn-BH, Bn-BH2
      |(one)? \s* (peak)? \s* merged                           
      |BBfl\d?
      |[NOS]?[A-Za-z]*-B(H\d?)?
      |\d?[A-Za-z]+
      |[Bc]+H\d?[ONB]H\d?
      |br\.?\s?[sdtqm]
      |\-?(NB|BN)
      |[ONS](Me|BH\d?)
    )
    \s* \) \s*
    (?:,|$)
''', re.VERBOSE)

B_pattern_B_x_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'B\s*[xX]*\s*\d+|'                # Bx2
        r'B-H\s*[xX]*\s*\d+|'              # B-Hx2
        r'B-Ar\s*[xX]*\s*\d+|'             # B-Arx2
        r'BAr\s*[xX]*\s*\d+|'              # BArx2
        r'BH\s*[xX]*\s*\d+|'               # BHx2
        r'BH2\s*[xX]*\s*\d+|'              # BH2x2
        r'BH3\s*[xX]*\s*\d+'               # BH3x2
    r'))\s*\)\s*(?:,|$)'
)

# 129.0 (2 x FH)
B_pattern_n_x_B = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'\d+\s*[xX]*\s*B\s*|'
        r'\d+\s*[xX]*\s*B-H\s*|'
        r'\d+\s*[xX]*\s*B-Ar\s*|'
        r'\d+\s*[xX]*\s*BAr\s*|'
        r'\d+\s*[xX]*\s*BH\s*|'
        r'\d+\s*[xX]*\s*BH2\s*|'
        r'\d+\s*[xX]*\s*BH3\s*'
    r'))\s*\)\s*(?:,|$)'
)

B_pattern_signal_type = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r's\s*|'
        r'd\s*|'
        r't\s*|'
        r'q\s*|'
        r'p\s*|'
        r'hept\s*|'
        r'broad\s*|'
        r'm\s*|'
        r'dd\s*|'
        r'dt\s*|'
        r'td\s*|'
        r'dq\s*|'
        r'qd\s*|'
        r'dp\s*|'
        r'pd\s*|'
        r'tp\s*|'
        r'dquint\s*|'
    r'))\s*\)\s*(?:,|$)'
) 

# example 25.4 (q, B4), 21.9 (s, B3), 18.5 (q, B4'), 18.5 (q, 2B)
B_pattern_shift_type_nB = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>(?:\d+B|B|B\d+\'?))\s*\)'
    r'\s*(?:,|$)'
)

# example 122 (2), 200(2)
B_pattern_shift_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*x*(?P<count>\d+)\s*\)\s*(?:,|$)'
)

B_pattern_shift = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*(?:,|$)'
)

B_pattern_full_J_2 = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 d, tt, AB…
      \s*,\s*
      J[A-Za-z]*\s*=\s*(?P<J>\d+(?:\.\d+)?)  # JHF、JAB 等
      \s*Hz
    \s*\)
''', re.VERBOSE)

# 匹配 -145 (dd, J = 56.6, 28.3 Hz, 2F, BF2) 这种格式
B_pattern_multi_J_with_B_count_and_ctype = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 dd
      \s*,\s*
      J\s*=\s*(?P<J1>\d+(?:\.\d+)?)\s*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz  # J = 56.6, 28.3 Hz
      \s*,\s*
      (?P<count>\d+B)              # 2B
      \s*,\s*
      (?P<ctype>[A-Za-z\d]+)         # 任意字母组合，如 BF2, CF3, ArF, etc.
    \s*\)
''', re.VERBOSE)

# 像氢谱的

B_PATTERN_TYPE2 = re.compile(r'''
    # chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount → optional pos
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*    # 可选2JFF\JFP\JF、J  etc。
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*B)
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # B: type → Fcount → [J?] → optional pos.可选J(FF)等
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*B)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?

      |
        # C: Fcount → type → [J?] → optional pos
        (?P<count3>\d+(?:\.\d+)?\s*B)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
        (?:\s*,\s*(?:[a-zA-Z0-9_=-]+))?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

B_PATTERN_TYPE1 = re.compile(
    r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J1>\d+(?:\.\d+)?)\s*Hz)?\s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*B)

      |
        # B: type → Fcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*B)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J2>\d+(?:\.\d+)?)\s*Hz)?

      |
        # C: Fcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*B)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*\d*J(?:[A-Za-z]+(?:[-,]?[A-Za-z]+)?)?\s*=\s*
        (?P<J3>\d+(?:\.\d+)?)\s*Hz)?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)

B_PATTERN_MULTY_J1 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        (?:\s*-?\d+\.\d+)
        (?:\s*-\s*-?\d+\.\d+)?
    )\s*
    \(\s*
    (?:
        # A: type → [J?] → Fcount
        (?P<type1>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J1>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*B)

      |
        # B: type → Fcount → [J?]
        (?P<type2>[A-Za-z'\s]+)\s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*B)
        (?:\s*,\s*J\s*=\s*
            (?P<J2>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # C: Fcount → type → [J?]
        (?P<count3>\d+(?:\.\d+)?\s*B)\s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*J\s*=\s*
            (?P<J3>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )   
      |
        # D: type → [J?] (no F count)
        (?P<type4>[A-Za-z'\s]+)\s*
        (?:\s*,\s*J\s*=\s*
            (?P<J4>
            (?:
                # —— 形式 A: 每个数后跟 Hz
                \d+(?:\.\d+)?\s*Hz
                (?:\s*,\s*\d+(?:\.\d+)?\s*Hz)*
            )
            |
            (?:
                # —— 形式 B: 一串数字，末尾统一跟 Hz
                \d+(?:\.\d+)?
                (?:\s*,\s*\d+(?:\.\d+)?)*\s*Hz
            )
            )
        )?
    )
    \s*\)
    (?:,|$)
    ''',
    re.IGNORECASE | re.VERBOSE
)         
    
B_PATTERN_NMR_MULTIJ2 = re.compile(r'''
    # 1. chemical shift (single or range)
    (?P<shift>
        -?\d+\.\d+(?:\s*-\s*-?\d+\.\d+)?      # e.g. -0.12 或 7.13-7.03
    )\s*
    \(\s*
    (?:
        # A: type → J-list → Fcount
        (?P<type1>[A-Za-z'\s]+)
        \s*,\s*
        (?P<J1>
            # 第一个 J=...
            J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
            # 后面可以跟若干 “, J=? 数字[Hz]”
            (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
        )
        \s*,\s*
        (?P<count1>\d+(?:\.\d+)?\s*B)

      |
        # B: type → Hcount → J-list
        (?P<type2>[A-Za-z'\s]+)
        \s*,\s*
        (?P<count2>\d+(?:\.\d+)?\s*B)
        (?:\s*,\s*
            (?P<J2>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?

      |
        # C: Fcount → type → J-list
        (?P<count3>\d+(?:\.\d+)?\s*B)
        \s*,\s*
        (?P<type3>[A-Za-z'\s]+)
        (?:\s*,\s*
            (?P<J3>
                J\s*=\s*\d+(?:\.\d+)?(?:\s*Hz)?
                (?:\s*,\s*(?:J\s*=\s*)?\d+(?:\.\d+)?(?:\s*Hz)? )*
            )
        )?
    )
    \s*\)
    (?:,|$)
''', re.IGNORECASE | re.VERBOSE)

B_pattern_handlers_11B = [
        (
            B_pattern_shift_range_ptype,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],   
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            B_pattern_shift_range_ptype_nB,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            B_pattern_shift_range_full,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            B_pattern_multi_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                [float(m.group('J1')), float(m.group('J2'))]
            )
        ),
        (
            B_pattern_full_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            B_pattern_full,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            B_pattern_full_Hz_nB,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            B_pattern_signal_type_nB_position,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            B_pattern_full_noHz,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            B_pattern_only_j,
            lambda m: (
                float(m.group('shift')),
                None,
                float(m.group('J'))
            )
        ),
        (
            B_pattern_full_nB,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            B_pattern_signal_ctye_j_ctype,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            B_pattern_B_type,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            B_pattern_B_x_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            B_pattern_n_x_B,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            B_pattern_signal_type,
            lambda m: (float(m.group('shift')), m.group('ctype'), None)
        ),
        (
            B_pattern_shift_type_nB,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            B_pattern_shift_number,
            lambda m: (float(m.group('shift')), None, None)
        ),       
        (
            B_pattern_full_J_2,
            lambda m: (float(m.group('shift')), m.group('ptype'), float(m.group('J')))
        ),
        (
            B_pattern_multi_J_with_B_count_and_ctype,
            lambda m: (float(m.group('shift')), m.group('ptype'), [float(m.group('J1')), float(m.group('J2'))])
        ),
    ]


def parse_shift_B(shift_str):
    """解析化学位移范围（修复版）"""

    match = SHIFT_PATTERN.search(shift_str)
    if not match:
        return (None, None)

    # 提取基础值
    first_val = float(match.group(1))
    second_val = float(match.group(2)) if match.group(2) else None

    # 处理范围逻辑
    if second_val is not None:
        min_shift = min(first_val, second_val)
        max_shift = max(first_val, second_val)
    else:
        min_shift = max_shift = first_val

    # 保留两位小数并返回正确顺序
    return (round(max_shift, 2), round(min_shift, 2))  # (max, min)

def parse_line_11B(line: str):
    line = re.sub(r'MHz', 'Hz', line)
    line = re.sub(r'\(CF3\)', '', line)
    line = re.sub(r', CF3', '', line)

    if line.endswith(' 13'):
        line = re.sub(r'\s*13$', '', line)

    matches = []  # will hold tuples (start, end, result)
    used_spans = []
    results = []
    # first pass: explicit patterns
    for pat, handler in B_pattern_handlers_11B:
        for m in pat.finditer(line):
            start, end = m.span()
            if pat in (B_pattern_full, B_pattern_full_J) and m.group('ptype') not in multiplet_dict:
                if multiplet_dict.get(m.group('ptype')) is None:
                    not_in_multi_dict.append(m.group('ptype'))
                continue
            if _overlaps(used_spans, start, end):
                continue
            matches.append((start, end, handler(m)))
            used_spans.append((start, end))

    # fallback simple shifts
    # mask matched spans
    masked = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        for m in B_pattern_shift.finditer(s_fb):
            st, ed = m.span()
            # if _overlaps(used_spans, st, ed):
            #     continue
            matches.append((st, ed, (float(m.group('shift')), None, None)))
            used_spans.append((st, ed))


    # sort all matches by original position
    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    # compute final unmatched
    masked_final = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked_final[i] = ' '
    unmatched = re.findall(r'\S+', ''.join(masked_final))

    results_2 = []
    used_spans_2 = []

    if len(unmatched) > 0:
        new_matches = []

        # unmatched 组合成新的 newline
        new_line = ' '.join(unmatched)
        # print(f"new_line: {new_line}")
        patterns = [
            (B_PATTERN_TYPE1, 'type1'),
            (B_PATTERN_TYPE2, 'type2'),
            (B_PATTERN_MULTY_J1, 'multyj1'),
            (B_PATTERN_NMR_MULTIJ2, 'multyj2'),
        ]

        for pat, _ in patterns:
            for m in pat.finditer(new_line):
                start, end = m.span()
                if _overlaps(used_spans_2, start, end):
                    continue
                shift_part = m.group('shift')
                max_shift, min_shift = parse_shift_B(shift_part)
                gd = m.groupdict()
                mnemonic = next((gd[k].strip() for k in ('type1','type2','type3','type4') if gd.get(k)), None)
                j_str = next((gd[k] for k in ('J1','J2','J3','J4') if gd.get(k)), None)
                j_values = []
                if j_str:
                    js = re.sub(r'Hz', '', j_str)
                    j_values = [f"{v.strip()}Hz" for v in js.split(',') if v.strip()]
                if multiplet_dict.get(mnemonic) is None:
                    not_in_multi_dict.append(mnemonic)
                new_matches.append((start, end, ([max_shift, min_shift], multiplet_dict.get(mnemonic), j_values)))
                used_spans_2.append((start, end))

        new_matches.sort(key=lambda x: x[0])
        results_2 = [res for _, _, res in new_matches]
        # print(f"results_2: {results_2}")
        masked = list(new_line)
        for start_matches, end_matches, _ in new_matches:
            start, end = start_matches, end_matches
            start = int(start)
            end = int(end)
            for i in range(start, end): masked[i] = ' '
        leftover = ''.join(masked)

        if re.fullmatch(r'[\d\.,\s\-]*', leftover):
            s_fb = leftover
            while True:
                m = B_pattern_shift.search(s_fb)
                if not m: break
                st, ed = m.span()
                if _overlaps(used_spans_2, st, ed):
                    s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
                    continue
                used_spans_2.append((st, ed))
                s_fb = s_fb[:st] + ' '*(ed-st) + s_fb[ed:]
            leftover = s_fb

        unmatched = re.findall(r'\S+', leftover)

    # 合并results_2和results
    results_all = results + results_2

    return results_all, unmatched

Si_pattern_shift_range_ptype = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>(?:br\.?\s?[sdtqm]|[^,\s()]+))\s*\)\s*(?:,|$)'
)

Si_pattern_shift_range_ptype_nSi = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*(?P<count>\d+)[Sis]\s*\)\s*(?:,|$)'
)

Si_pattern_shift_range_full = re.compile(
    r'(?P<shift1>\s*-?\d+(?:\.\d+)?)\s*-\s*(?P<shift2>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

Si_pattern_multi_J = re.compile( 
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*'
    r'(?P<J1>\d+(?:\.\d+)?)\s*(Hz)*,\s*(?P<J2>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

# JFF等
Si_pattern_full_J = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J[FcPpFf][-,]?[FcPpFf]\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*(Hz)?\s*\)\s*(?:,|$)'
)

Si_pattern_full = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

Si_pattern_full_Hz_nSi = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*,\s*'
    r'(?P<count>\d)Si\s*\)\s*(?:,|$)'
)

# 119.9 (d, 2F, F17)
Si_pattern_signal_type_nSi_position = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>\d)?Si\s*,\s*Si(?P<position>\d+)\s*\)\s*(?:,|$)'
)

Si_pattern_full_noHz = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<ptype>[^,\s()]+)\s*,\s*\d*J\s*=\s*(?P<J>\d+(?:\.\d+)?)\s*\)\s*(?:,|$)'
)

Si_pattern_only_j = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*\d*J(\s?[FcPpFf][-,]?[FcPpFf])?\s*=\s*'
    r'(?P<J>\d+(?:\.\d+)?)\s*Hz\s*\)\s*(?:,|$)'
)

Si_pattern_full_nSi = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*(?P<count>\d+)\s?[Sis]\s*\)\s*(?:,|$)'
)


Si_pattern_Si_x_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'Si\s*[xX]*\s*\d+|'                # Si x2
        r'Si-Ar\s*[xX]*\s*\d+|'             # Si-Ar x2
        r'SiAr\s*[xX]*\s*\d+|'              # SiAr x2
        r'SiH\s*[xX]*\s*\d+|'               # SiH x2
        r'SiH2\s*[xX]*\s*\d+|'              # SiH2 x2
        r'SiH3\s*[xX]*\s*\d+'               # SiH3 x2
    r'))\s*\)\s*(?:,|$)'
)

# 129.0 (2 x SiH)
Si_pattern_n_x_Si = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r'\d+\s*[xX]*\s*Si\s*|'
        r'\d+\s*[xX]*\s*Si-H\s*|'
        r'\d+\s*[xX]*\s*Si-Ar\s*|'
        r'\d+\s*[xX]*\s*SiAr\s*|'
            r'\d+\s*[xX]*\s*SiH\s*|'
        r'\d+\s*[xX]*\s*SiH2\s*|'
        r'\d+\s*[xX]*\s*SiH3\s*'
    r'))\s*\)\s*(?:,|$)'
)

Si_pattern_signal_type = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*'
    r'(?P<ctype>('
        r's\s*|'
        r'd\s*|'
        r't\s*|'
        r'q\s*|'
        r'p\s*|'
        r'hept\s*|'
        r'broad\s*|'
        r'm\s*|'
        r'dd\s*|'
        r'dt\s*|'
        r'td\s*|'
        r'dq\s*|'
        r'qd\s*|'
        r'dp\s*|'
        r'pd\s*|'
        r'tp\s*|'
        r'dquint\s*|'
    r'))\s*\)\s*(?:,|$)'
) 

# example 25.4 (q, P4), 21.9 (s, P3), 18.5 (q, P4'), 18.5 (q, 2P)
Si_pattern_shift_type_nSi = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*'
    r'\(\s*(?P<ptype>[^,\s()]+)\s*,\s*'
    r'(?P<count>(?:\d+Si|Si|Si\d+\'?))\s*\)'
    r'\s*(?:,|$)'
)

# example 122 (2), 200(2)
Si_pattern_shift_number = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*\(\s*x*(?P<count>\d+)\s*\)\s*(?:,|$)'
)

Si_pattern_shift = re.compile(
    r'(?P<shift>\s*-?\d+(?:\.\d+)?)\s*(?:,|$)'
)


Si_pattern_full_J_2 = re.compile(r'''
    (?P<shift>-?\d+(?:\.\d+)?)     # 化学位移
    \s*\(\s*                       
      (?P<ptype>[A-Za-z]+)         # 拓扑类型，例如 d, tt, AB…
      \s*,\s*
      J[A-Za-z]*\s*=\s*(?P<J>\d+(?:\.\d+)?)  # JHF、JAB 等
      \s*Hz
    \s*\)
''', re.VERBOSE)


Si_pattern_handlers_Si = [
        (
            Si_pattern_shift_range_ptype,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],   
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            Si_pattern_shift_range_ptype_nSi,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            Si_pattern_shift_range_full,
            lambda m: (
                [float(m.group('shift1')), float(m.group('shift2'))],
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            Si_pattern_multi_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                [float(m.group('J1')), float(m.group('J2'))]
            )
        ),
        (
            Si_pattern_full_J,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            Si_pattern_full,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            Si_pattern_full_Hz_nSi,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            Si_pattern_signal_type_nSi_position,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                None
            )
        ),
        (
            Si_pattern_full_noHz,
            lambda m: (
                float(m.group('shift')),
                m.group('ptype') if m.group('ptype') in multiplet_dict else None,
                float(m.group('J'))
            )
        ),
        (
            Si_pattern_only_j,
            lambda m: (
                float(m.group('shift')),
                None,
                float(m.group('J'))
            )
        ),
        (
            Si_pattern_full_nSi,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            Si_pattern_Si_x_number,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            Si_pattern_n_x_Si,
            lambda m: (float(m.group('shift')), None, None)
        ),
        (
            Si_pattern_signal_type,
            lambda m: (float(m.group('shift')), m.group('ctype'), None)
        ),
        (
            Si_pattern_shift_type_nSi,
            lambda m: (float(m.group('shift')), m.group('ptype'), None)
        ),
        (
            Si_pattern_shift_number,
            lambda m: (float(m.group('shift')), None, None)
        ),       
        (
            Si_pattern_full_J_2,
            lambda m: (float(m.group('shift')), m.group('ptype'), float(m.group('J')))
        ),
    ]
  
def parse_line_Si(line: str):
    line = re.sub(r'MHz', 'Hz', line)

    matches = []  # will hold tuples (start, end, result)
    used_spans = []

    # first pass: explicit patterns
    for pat, handler in Si_pattern_handlers_Si:
        for m in pat.finditer(line):
            start, end = m.span()
            if pat in (Si_pattern_full, Si_pattern_full_J) and m.group('ptype') not in multiplet_dict:
                continue
            if _overlaps(used_spans, start, end):
                continue
            matches.append((start, end, handler(m)))
            used_spans.append((start, end))

    # fallback simple shifts
    # mask matched spans
    masked = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked[i] = ' '
    leftover = ''.join(masked)

    if re.fullmatch(r'[\d\.,\s\-]*', leftover):
        s_fb = leftover
        for m in Si_pattern_shift.finditer(s_fb):
            st, ed = m.span()
            # if _overlaps(used_spans, st, ed):
            #     continue
            matches.append((st, ed, (float(m.group('shift')), None, None)))
            used_spans.append((st, ed))

    # sort all matches by original position
    matches.sort(key=lambda x: x[0])
    results = [res for _, _, res in matches]

    # compute final unmatched
    masked_final = list(line)
    for start, end, _ in matches:
        for i in range(start, end):
            masked_final[i] = ' '
    unmatched = re.findall(r'\S+', ''.join(masked_final))

    return results, unmatched

# 新建nmr_processed列
df['nmr_processed'] = None
df['C_num_max'] = None
df['C_num_min'] = None
df['C_num_str'] = None
df['C_count_correct'] = None

total_unmatched_H = 0
total_matched_H = 0
matched_list_H = []
unmatched_list_H = []

total_unmatched_C = 0
total_matched_C = 0
matched_list_C = []
unmatched_list_C = []

total_unmatched_F = 0
total_matched_F = 0
matched_list_F = []
unmatched_list_F = []

matched_list_P = []
unmatched_list_P = []
total_matched_P = 0
total_unmatched_P = 0

matched_list_B = []
unmatched_list_B = []
total_matched_B = 0
total_unmatched_B = 0

matched_list_Si = []
unmatched_list_Si = []
total_matched_Si = 0
total_unmatched_Si = 0

def calc_H_count(signal_text):
    """解析氢数"""
    total_h = 0.0
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*H\b", signal_text)
    total_h += sum(float(num) for num in matches)
    return total_h

def calc_C_count(signal_list):
    if signal_list is None:
        return 0
    """解析碳的峰数"""
    return len(signal_list)

def calc_C_num_smiles_max(smiles):
    """解析 SMILES 中的碳原子数"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"无效的 SMILES: {smiles}")
    # 只统计符号为 'C' 的原子
    return sum(1 for atom in mol.GetAtoms() if atom.GetSymbol() == 'C')

def calc_C_num_smiles_min(smiles) -> int:
    """
    解析 SMILES 中的碳原子等价类别数。
    例如苯 C1=CC=CC=C1 会返回 1，因为 6 个 C 在对称性分群后只是一类。
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"无效的 SMILES: {smiles}")

    # 获取每个原子的对称性等级
    # breakTies=False 保证真正拓扑等价的原子打相同等级
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))

    # 收集所有碳原子的等级，并去重
    equiv_classes = {r for atom, r in zip(mol.GetAtoms(), ranks)
                     if atom.GetSymbol() == 'C'}

    # 返回等价类别数
    return len(equiv_classes)


chunk_size = 10_000
num_chunks = int(np.ceil(len(df) / chunk_size))

# 拆分 df 为多个小块
df_chunks = [df.iloc[i*chunk_size:(i+1)*chunk_size].copy() for i in range(num_chunks)]

# 每个子进程处理的函数
def process_chunk(chunk):
    # 复制一份，避免原地改到主进程的 df（虽然在子进程里也行）
    chunk = chunk.copy()

    chunk['nmr_processed'] = None
    chunk['C_num_str']    = None
    chunk['C_num_max']    = None
    chunk['C_num_min']    = None

    # 所有用于累计的变量必须在函数内部初始化
    for index, row in chunk.iterrows():
        if row['nmr_type'] == '1H NMR':
            line = row['nmr_shift']
            results, unmatched = parse_nmr_signals_H(line)
            # print(f"results: {results}")
            # print(f"unmatched: {unmatched}")
            if unmatched:
                chunk.at[index, 'nmr_processed'] = "unmatched"
            else:
                chunk.at[index, 'nmr_processed'] = str(results)
        
        elif row['nmr_type'] == '13C NMR':
            line = row['nmr_shift']
            if line is not None:
                results, unmatched = parse_line(line)
            else:
                results = None
                unmatched = None

            if isinstance(unmatched, list) and unmatched:
                chunk.at[index, 'nmr_processed'] = "unmatched"
            else:
                chunk.at[index, 'nmr_processed'] = str(results)
                chunk.at[index, 'C_num_str'] = calc_C_count(results)
                chunk.at[index, 'C_num_max'] = calc_C_num_smiles_max(row['smiles'])
                chunk.at[index, 'C_num_min'] = calc_C_num_smiles_min(row['smiles'])

        elif row['nmr_type'] == '19F NMR':
            line = row['nmr_shift']
            results, unmatched = parse_line_19F(line) if line else (None, None)
            chunk.at[index, 'nmr_processed'] = "unmatched" if unmatched else str(results)

        elif 'P NMR' in row['nmr_type']:
            line = row['nmr_shift']
            results, unmatched = parse_line_31P(line) if line else (None, None)
            chunk.at[index, 'nmr_processed'] = "unmatched" if unmatched else str(results)

        elif 'B NMR' in row['nmr_type']:
            line = row['nmr_shift']
            results, unmatched = parse_line_11B(line) if line else (None, None)
            chunk.at[index, 'nmr_processed'] = "unmatched" if unmatched else str(results)

        elif  'Si NMR'in row['nmr_type']:
            line = row['nmr_shift']
            results, unmatched = parse_line_Si(line) if line else (None, None)
            chunk.at[index, 'nmr_processed'] = "unmatched" if unmatched else str(results)

        else:
            chunk.at[index, 'nmr_processed'] = "unmatched"

    return chunk

# 并行执行
with ProcessPoolExecutor(max_workers=60) as executor:
    results = list(tqdm(executor.map(process_chunk, df_chunks), total=len(df_chunks)))

# 合并结果
df_result = pd.concat(results, ignore_index=True)

# 保存
df_result.to_parquet(final_result_parquet, index=False)


def is_true_float(x):
    try:
        x_str = str(x)
        float_val = float(x_str)
        # 关键点：float 形式，并且含有小数点（即不是整数）
        return '.' in x_str or not float_val.is_integer()
    except:
        return False


# 判断是否单调
def is_monotonic(seq, tol=1e-8):
    seq = [float(x) for x in seq]
    increasing = all(x <= y or abs(x - y) < tol for x, y in zip(seq, seq[1:]))
    decreasing = all(x >= y or abs(x - y) < tol for x, y in zip(seq, seq[1:]))
    return increasing or decreasing

def should_extract(processed):
    try:
        # 有些字段可能是字符串格式的，需要转换
        if isinstance(processed, str):
            processed = ast.literal_eval(processed)
        
        avg_vals = []
        for item in processed:
            if not (len(item) >= 5):
                return False  # 缺项了也提取
            val1, val2 = item[-2], item[-1]
            if not (is_true_float(val1) and is_true_float(val2)):
                print(f"val1: {val1}, val2: {val2}")
                return False  # 条件1
            avg = (float(val1) + float(val2)) / 2
            avg_vals.append(avg)
        
        # 条件2：不是单调序列
        if not is_monotonic(avg_vals):
            # print(f"avg_vals: {avg_vals}")
            return False

        return True  # 提取
    except Exception as e:
        # 解析失败的也提取
        return False

def should_extract_others(processed):
    try:
        # 有些字段可能是字符串格式的，需要转换
        if isinstance(processed, str):
            processed = ast.literal_eval(processed)
        
        avg_vals = []
        for item in processed:
            if not (len(item) >= 3):
                return False  # 缺项了也提取
            val = item[0]
            if not is_true_float(val):
                return False  # 条件1
            avg_vals.append(float(val))
        
        # 条件2：不是单调序列
        if not is_monotonic(avg_vals):
            return False

        return True  # 提取
    except Exception as e:
        # 解析失败的也提取
        return False


# 读取 parquet
df = pd.read_parquet(os.path.join(work_dir, "final_result_0715_1.parquet"))

# 过滤掉 unmatched 的行
filtered_unmatched = df[df["nmr_processed"] != "unmatched"]
filtered_H = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("H")]
filtered_C = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("C")]
filtered_F = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("F")]
filtered_P = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("P")]
filtered_B = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("B")]
filtered_Si = filtered_unmatched[filtered_unmatched["nmr_type"].str.contains("Si")]


from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor

def parallel_filter(df, func, col, max_workers=60):
    """
    并行过滤：对 df[col] 的每个值执行 func，并返回布尔过滤后的 df。
    注意：只将必要数据（列值）传入子进程，避免整体拷贝 DataFrame。
    """
    data = df[col].tolist()  # 仅提取需要处理的一列
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(tqdm(executor.map(func, data), total=len(data)))
    return df[pd.Series(results, index=df.index)]

extracted_correct_H = parallel_filter(filtered_H, should_extract, "nmr_processed", max_workers=max_works)
extracted_correct_C = parallel_filter(filtered_C, should_extract_others, "nmr_processed", max_workers=max_works)
extracted_correct_F = parallel_filter(filtered_F, should_extract_others, "nmr_processed", max_workers=max_works)
extracted_correct_P = parallel_filter(filtered_P, should_extract_others, "nmr_processed", max_workers=max_works)
extracted_correct_B = parallel_filter(filtered_B, should_extract_others, "nmr_processed", max_workers=max_works)
extracted_correct_Si = parallel_filter(filtered_Si, should_extract_others, "nmr_processed", max_workers=max_works)

# 补集为错误结果
extracted_error_H = filtered_H[~filtered_H["nmr_processed"].isin(extracted_correct_H["nmr_processed"])]
extracted_error_C = filtered_C[~filtered_C["nmr_processed"].isin(extracted_correct_C["nmr_processed"])]
extracted_error_F = filtered_F[~filtered_F["nmr_processed"].isin(extracted_correct_F["nmr_processed"])]
extracted_error_P = filtered_P[~filtered_P["nmr_processed"].isin(extracted_correct_P["nmr_processed"])]
extracted_error_B = filtered_B[~filtered_B["nmr_processed"].isin(extracted_correct_B["nmr_processed"])]
extracted_error_Si = filtered_Si[~filtered_Si["nmr_processed"].isin(extracted_correct_Si["nmr_processed"])]

# 保存为 csv
extracted_correct_H.to_csv(os.path.join(work_dir, "filtered_results_H_0715_1.csv"), index=False)
extracted_correct_C.to_csv(os.path.join(work_dir, "filtered_results_C_0715_1.csv"), index=False)
extracted_correct_F.to_csv(os.path.join(work_dir, "filtered_results_F_0715_1.csv"), index=False)
extracted_correct_P.to_csv(os.path.join(work_dir, "filtered_results_P_0715_1.csv"), index=False)
extracted_correct_B.to_csv(os.path.join(work_dir, "filtered_results_B_0715_1.csv"), index=False)
extracted_correct_Si.to_csv(os.path.join(work_dir, "filtered_results_Si_0715_1.csv"), index=False)
extracted_error_H.to_csv(os.path.join(work_dir, "filtered_results_H_error_0715_1.csv"), index=False)
extracted_error_C.to_csv(os.path.join(work_dir, "filtered_results_C_error_0715_1.csv"), index=False)
extracted_error_F.to_csv(os.path.join(work_dir, "filtered_results_F_error_0715_1.csv"), index=False)
extracted_error_P.to_csv(os.path.join(work_dir, "filtered_results_P_error_0715_1.csv"), index=False)
extracted_error_B.to_csv(os.path.join(work_dir, "filtered_results_B_error_0715_1.csv"), index=False)
extracted_error_Si.to_csv(os.path.join(work_dir, "filtered_results_Si_error_0715_1.csv"), index=False)

print(f"提取完成，共 {len(extracted_correct_H)} 行，已保存为 filtered_results_H_0715_1.csv")
print(f"提取完成，共 {len(extracted_correct_C)} 行，已保存为 filtered_results_C_0715_1.csv")
print(f"提取完成，共 {len(extracted_correct_F)} 行，已保存为 filtered_results_F_0715_1.csv")
print(f"提取完成，共 {len(extracted_correct_P)} 行，已保存为 filtered_results_P_0715_1.csv")
print(f"提取完成，共 {len(extracted_correct_B)} 行，已保存为 filtered_results_B_0715_1.csv")
print(f"提取完成，共 {len(extracted_correct_Si)} 行，已保存为 filtered_results_Si_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_H)} 行，已保存为 filtered_results_H_error_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_C)} 行，已保存为 filtered_results_C_error_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_F)} 行，已保存为 filtered_results_F_error_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_P)} 行，已保存为 filtered_results_P_error_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_B)} 行，已保存为 filtered_results_B_error_0715_1.csv")
print(f"提取完成，共 {len(extracted_error_Si)} 行，已保存为 filtered_results_Si_error_0715_1.csv")

# 将所有核素的结果全部合并
extracted_correct_all = pd.concat([extracted_correct_H, extracted_correct_C, extracted_correct_F, extracted_correct_P, extracted_correct_B, extracted_correct_Si])
extracted_error_all = pd.concat([extracted_error_H, extracted_error_C, extracted_error_F, extracted_error_P, extracted_error_B, extracted_error_Si])

# 保存
extracted_correct_all.to_parquet(os.path.join(work_dir, "filtered_results_all_0715_1.parquet"), index=False)
extracted_error_all.to_parquet(os.path.join(work_dir, "filtered_results_all_error_0715_1.parquet"), index=False)


"""
now we have get a parquet file with the NMR signals
then we need to do some other cleaning
"""




import pandas as pd
import ast
from collections import Counter
import json
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from rdkit import Chem

from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')

from rdkit.Chem import rdmolops
from rdkit.Chem import CanonicalRankAtoms 


allowed_list = sorted(set(multiplet_dict.keys()))
print(allowed_list)

# 删除 J=...Hz / hz 的表达式（允许多个、逗号分隔）
def clean_j_coupling(j_str):
    if not isinstance(j_str, str):
        return j_str
    # 删除所有形如 J = 7.5 Hz 的内容
    j_str = re.sub(r'\s*J\s*=\s*', '', j_str)
    # 删除孤立的 Hz 或 hz
    j_str = re.sub(r'HZ', '', j_str)
    j_str = re.sub(r'hz', '', j_str)
    # 删除多余逗号或空格
    j_str = re.sub(r'\s*,\s*', ', ', j_str)  # 统一逗号后空格格式
    j_str = j_str.strip(', ').strip()
    return j_str

def count_hydrogens(nmr_data: str) -> float:
    total_h = 0.0
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*[HН]\b", nmr_data)
    total_h += sum(float(num) for num in matches)
    if isinstance(total_h, float) and total_h.is_integer():
        total_h = int(total_h)
    return total_h

def calc_H_num_smiles_min(smiles) -> int:
    """
    解析 SMILES 中氢原子的等价类别数。
    对于添加显式氢后的分子，使用 CanonicalRankAtoms 判断拓扑环境。
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"无效的 SMILES: {smiles}")

    mol_H = Chem.AddHs(mol)
    ranks = list(Chem.CanonicalRankAtoms(mol_H, breakTies=False))

    H_env_set = set()

    for atom in mol_H.GetAtoms():
        if atom.GetAtomicNum() == 1:  # H
            neighbor = atom.GetNeighbors()[0]
            bond = mol_H.GetBondBetweenAtoms(atom.GetIdx(), neighbor.GetIdx())

            env_key = (
                ranks[atom.GetIdx()],         # 氢的 rank
                ranks[neighbor.GetIdx()],     # 邻居的 rank
                neighbor.GetAtomicNum(),      # 邻居元素
                bond.GetBondType(),           # 键类型
                neighbor.GetHybridization(),  # 邻居杂化态
                neighbor.GetDegree(),         # 邻居连接度
            )
            H_env_set.add(env_key)

    return len(H_env_set)



"""
in this step, we applied rules:
1, if the smiles is not valid, then drop the row
2, if the format of nmr_processed signal is not correct, then drop the row
3, if the multiplet is not in the allowed_list, this record is likely incorrect, so we delete this row.
"""

def process_chunk(chunk_df):

    chunk = chunk_df.copy()
    chunk['atom_number'] = None
    chunk['atom_number_diff_env'] = None
    chunk['atom_number_abstract'] = None

    for index, row in chunk_df.iterrows():
        smiles = row['smiles']
        try:
            mol = Chem.MolFromSmiles(smiles)
        except Exception:
            # 从chunk中删除该行
            chunk = chunk.drop(index, errors='ignore')
            continue

        if mol is None:
            chunk = chunk.drop(index, errors='ignore')
            continue
        
        if row['nmr_type'] == "1H NMR":
            try:
                line = ast.literal_eval(row["nmr_processed"])
                if not isinstance(line, list):
                    chunk = chunk.drop(index, errors='ignore')
                    continue
            
            except Exception:
                chunk = chunk.drop(index, errors='ignore')
                continue

            for idx, i in enumerate(line):
                try:
                    if isinstance(i, str):
                        i = ast.literal_eval(i)
                    if not isinstance(i, tuple):
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    if len(i) < 5:
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    
                    if i[0] not in allowed_list:
                        chunk = chunk.drop(index, errors='ignore')
                        continue

                    str_j = str(i[1])
                    str_h_num = str(i[2])
                    if str_h_num == "0H":
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    elif str_h_num == None:
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    
                    if "J" in str_j or "HZ" in str_j or "hz" in str_j:
                        str_j = clean_j_coupling(str_j)
                    # 我现在要把更新后的str_j带回line，然后更新chunk
                        new_i = (i[0], str_j, *i[2:])
                        line[idx] = new_i

                        chunk.at[index, 'nmr_processed'] = line

                except Exception as e:
                    chunk = chunk.drop(index, errors='ignore')
                    continue

            mol_H = Chem.AddHs(mol)

            # 1) 所有氢原子列表
            H_atoms = [a for a in mol_H.GetAtoms() if a.GetAtomicNum() == 1]
            # 2) 总氢数
            atom_number = len(H_atoms)

            # 3) 唯一环境数 = 不同 rank 的 H 数
            ranks = list(Chem.CanonicalRankAtoms(mol_H, breakTies=False))

            H_env_set = set()

            for atom in mol_H.GetAtoms():
                if atom.GetAtomicNum() == 1:  # H
                    neighbors = atom.GetNeighbors()
                    if not neighbors:
                        chunk = chunk.drop(index, errors='ignore') 
                        continue  # 跳过没有邻居的氢（通常是错误结构）
                    neighbor = neighbors[0]
                    bond = mol_H.GetBondBetweenAtoms(atom.GetIdx(), neighbor.GetIdx())

                    env_key = (
                        ranks[atom.GetIdx()],
                        ranks[neighbor.GetIdx()],
                        neighbor.GetAtomicNum(),
                        bond.GetBondType(),
                        neighbor.GetHybridization(),
                        neighbor.GetDegree(),
                    )
                    H_env_set.add(env_key)
            unique_envs_count = len(H_env_set)
            chunk.at[index, 'atom_number'] = atom_number
            chunk.at[index, 'atom_number_diff_env'] = unique_envs_count
            chunk.at[index, 'atom_number_abstract'] = count_hydrogens(row['nmr_shift'])

        else:

            target_element = None
            if "C" in row['nmr_type']:
                target_element = 'C'
            elif "F" in row['nmr_type']:
                target_element = 'F'
            elif "Si" in row['nmr_type']:
                target_element = 'Si'
            elif "B" in row['nmr_type']:
                target_element = 'B'
            elif "P" in row['nmr_type']:
                target_element = 'P'
            
            if target_element is None:
                chunk = chunk.drop(index, errors='ignore')
                continue
            
            try:
                line = ast.literal_eval(row["nmr_processed"])

                if not isinstance(line, list):
                    chunk = chunk.drop(index, errors='ignore')
                    continue
                
            except Exception:
                chunk = chunk.drop(index, errors='ignore')
                continue

            for i in line:
                try:
                    if isinstance(i, str):
                        i = ast.literal_eval(i)
                    if not isinstance(i, tuple):
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    if len(i) < 3:
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    if i[0] == None:
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                    if i[1] not in allowed_list and i[1] != None:
                        print(i[1])
                        chunk = chunk.drop(index, errors='ignore')
                        continue
                except Exception:
                    chunk = chunk.drop(index, errors='ignore')
                    continue  # 不要忘记 continue 否则后面仍然会运行

            mol_C = Chem.RemoveHs(mol)
            atom_number = sum(1 for atom in mol_C.GetAtoms() if atom.GetSymbol() == target_element)
            ranks = list(Chem.CanonicalRankAtoms(mol_C, breakTies=False))
            # 收集所有碳原子的等级，并去重
            equiv_classes = {r for atom, r in zip(mol_C.GetAtoms(), ranks)
                            if atom.GetSymbol() == target_element}
            chunk.at[index, 'atom_number'] = atom_number
            chunk.at[index, 'atom_number_diff_env'] = len(equiv_classes)
            chunk.at[index, 'atom_number_abstract'] = len(line)
            
    return chunk

# 将 DataFrame 切块
chunk_size = 5000
chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

# 多进程处理 + tqdm
results = []


with Pool(processes = max_works) as pool:
    for res in tqdm(pool.imap_unordered(process_chunk, chunks), total=len(chunks)):
        results.append(res)

# 合并所有结果
df_final = pd.concat(results, ignore_index=True)

df_final['nmr_processed'] = df_final['nmr_processed'].apply(lambda x: str(x))

# 保存为 Parquet 文件
df_final.to_parquet(os.path.join(work_dir, "processed_results_0715_1_preview.parquet"), index=False)



"""
in this step, we applied rules:
if the atom number is 0, this record is incorrect, so we delete this molecule.
"""


# 读取 Parquet 文件
input_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0715_copy/processed_results_0715_1_preview_cleaned.parquet"
df = pd.read_parquet(input_path)

# 筛选 atom_number 为 0 的行（无论是 int 还是 float）
df_zero_atoms = df[df['atom_number'] == 0]

# 保存为 CSV 文件
output_csv = input_path.replace(".parquet", "_atom_number_0.csv")
df_zero_atoms.to_csv(output_csv, index=False)

print(f"筛选完成，已保存 {len(df_zero_atoms)} 行到：{output_csv}")

# 路径设置
parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0715_copy/processed_results_0715_1_preview_cleaned.parquet"
csv_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0715_copy/processed_results_0715_1_preview_cleaned_atom_number_0.csv"

# 读取数据
df_full = pd.read_parquet(parquet_path)
df_to_remove = pd.read_csv(csv_path)

# 为了确保比较一致，删除前先去除两列中的空格并统一为字符串
df_full['filename'] = df_full['filename'].astype(str).str.strip()
df_full['smiles'] = df_full['smiles'].astype(str).str.strip()
df_to_remove['filename'] = df_to_remove['filename'].astype(str).str.strip()
df_to_remove['smiles'] = df_to_remove['smiles'].astype(str).str.strip()

# 合并两个字段作为唯一标识
df_full['key'] = df_full['filename'] + '||' + df_full['smiles']
df_to_remove['key'] = df_to_remove['filename'] + '||' + df_to_remove['smiles']

# 构造要保留的掩码
mask_keep = ~df_full['key'].isin(set(df_to_remove['key']))

# 过滤并删除
df_filtered = df_full[mask_keep].drop(columns=['key'])

# 保存结果
output_path = parquet_path.replace(".parquet", "_filtered.parquet")
df_filtered.to_parquet(output_path, index=False)

print(f"删除完成，保留 {len(df_filtered)} 行，结果已保存至：{output_path}")




"""
in this step, we applied rules:
1, if the smiles contains '*', then drop the row
2, for molecule with elements only C, H, O, N, S, Cl, Br, I, if the J value is not in the range of 0.4-30, then drop the row
3, for molecule with elements only C, H, O, N, S, Cl, Br, I, if the H shift value is not in the range of -5-25, then drop the row
4, for molecule with elements only C, H, O, N, S, Cl, Br, I, if the C shift value is not in the range of -20-250, then drop the row
"""

parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0715_copy/processed_results_0715_1_preview_cleaned_filtered.parquet"
# 读取数据
df = pd.read_parquet(parquet_path)
print(df.head())
print(f"df.shape: {df.shape}")

# 删除含有 '*' 的 smiles 行
df_filtered = df[~df['smiles'].astype(str).str.contains(r'\*')]
print(df_filtered.head())
print(f"df_filtered.shape: {df_filtered.shape}")

# 保存为新的 Parquet 文件
output_path = parquet_path.replace("_1_preview_cleaned_filtered.parquet", "_wait_j.parquet")
df_filtered.to_parquet(output_path, index=False)

print(f"删除含 * 的 smiles 行后，保留 {len(df_filtered)} 行，已保存至：{output_path}")

import pandas as pd
import ast
from collections import Counter
import json
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from rdkit import Chem

parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0715_copy/processed_results_0715_wait_j.parquet"

df = pd.read_parquet(parquet_path)

# H coupling range 0-30
# H shift range
# C shift range

allowed_elements = {"H", "C", "O", "N", "S", "Cl", "Br", "I"}

def is_valid_smiles(smiles, allowed_elements):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        elements_in_mol = {atom.GetSymbol() for atom in mol.GetAtoms()}
        return elements_in_mol.issubset(allowed_elements)
    except:
        return False

def process_chunk(chunk_df):
    chunk = chunk_df.copy()
    J_H_list = []
    shift_H_list = []
    shift_C_list = []
    notice_j_chunk = []
    notice_shift_H_chunk = []
    notice_shift_C_chunk = []
    for index, row in chunk.iterrows():
        smiles = row["smiles"]
        if not is_valid_smiles(smiles, allowed_elements):
            continue

        if "H" in row["nmr_type"]:
            # 如果所有元素都在 allowed_elements 中，则继续
            line = ast.literal_eval(row["nmr_processed"])
            line_is_error = False
            for i in line:
                if isinstance(i, str):
                    i = ast.literal_eval(i)
                if not isinstance(i, tuple):
                    continue
                if len(i) < 5:
                    continue

                j_list = i[1]
                if isinstance(j_list, str):
                    j_list = ast.literal_eval(j_list)
                    for j_value in j_list:
                        j_value = re.sub(r'[jJ]\s*=\s*|\s*[Hh][Zz]', '', j_value)
                        j_value = float(j_value)
                        if j_value < 0.4 or j_value > 30:
                            line_is_error = True
                            notice_j_chunk.append(row)
                if not isinstance(j_list, list):
                    continue
                J_H_list.extend(j_list)

                shift_max = i[3]
                shift_min = i[4]
                shift_h = (float(shift_max) + float(shift_min)) / 2
                if shift_h < -5 or shift_h > 25:
                    line_is_error = True
                    notice_shift_H_chunk.append(row)
                shift_H_list.append(shift_h)
            
            if line_is_error:
                chunk = chunk.drop(index, errors='ignore')
                continue
        
        elif "C" in row["nmr_type"]:
            line = ast.literal_eval(row["nmr_processed"])
            row_is_error = False
            for i in line:
                if isinstance(i, str):
                    i = ast.literal_eval(i)
                if not isinstance(i, tuple):
                    continue
                if len(i) < 3:
                    continue
                
                try:
                    shift_c = float(i[0])
                    if shift_c < -20 or shift_c > 250:
                        row_is_error = True
                    shift_C_list.append(shift_c)
                except:
                    continue
            if row_is_error:
                notice_shift_C_chunk.append(row)
                chunk = chunk.drop(index, errors='ignore')
                continue

    return J_H_list, shift_H_list, shift_C_list, notice_j_chunk, notice_shift_H_chunk, notice_shift_C_chunk, chunk

# 将 DataFrame 切块
chunk_size = 5000
chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

H_coupling_total_results = []
H_shift_total_results = []
C_shift_total_results = []
error_j_total_results = []
error_shift_H_total_results = []
error_shift_C_total_results = []

new_chunk_total_results = []

from multiprocessing import Pool
from tqdm import tqdm

with Pool(processes=60) as pool:
    for res in tqdm(pool.imap_unordered(process_chunk, chunks), total=len(chunks)):
        J_H_chunk, shift_H_chunk, shift_C_chunk, err_j, err_H, err_C, filtered_chunk = res

        H_coupling_total_results.extend(J_H_chunk)
        H_shift_total_results.extend(shift_H_chunk)
        C_shift_total_results.extend(shift_C_chunk)
        error_j_total_results.extend(err_j)
        error_shift_H_total_results.extend(err_H)
        error_shift_C_total_results.extend(err_C)

        if isinstance(filtered_chunk, pd.DataFrame):
            new_chunk_total_results.append(filtered_chunk)
        else:
            print(f"[警告] 非DataFrame类型跳过: {type(filtered_chunk)}")

H_J_save_path = parquet_path.replace("_wait_j.parquet", "_H_J_CHON.csv")
H_shift_save_path = parquet_path.replace("_wait_j.parquet", "_H_shift_CHON.csv")
C_shift_save_path = parquet_path.replace("_wait_j.parquet", "_C_shift_CHON.csv")
error_j_save_path = parquet_path.replace("_wait_j.parquet", "_notice_j.csv")
error_shift_H_save_path = parquet_path.replace("_wait_j.parquet", "_notice_shift_H.csv")
error_shift_C_save_path = parquet_path.replace("_wait_j.parquet", "_notice_shift_C.csv")
new_chunk_save_path = parquet_path.replace("_wait_j.parquet", "_final_1.parquet")

# 计数并且按照出现次数排序
H_J_counts = Counter(H_coupling_total_results)
H_J_counts_sorted = sorted(H_J_counts.items(), key=lambda x: x[1], reverse=True)

H_shift_counts = Counter(H_shift_total_results)
H_shift_counts_sorted = sorted(H_shift_counts.items(), key=lambda x: x[1], reverse=True)

C_shift_counts = Counter(C_shift_total_results)
C_shift_counts_sorted = sorted(C_shift_counts.items(), key=lambda x: x[1], reverse=True)

# 合并所有 DataFrame
final_df = pd.concat(new_chunk_total_results, ignore_index=True)

pd.DataFrame(H_J_counts_sorted).to_csv(H_J_save_path, index=False)
pd.DataFrame(H_shift_counts_sorted).to_csv(H_shift_save_path, index=False)
pd.DataFrame(C_shift_counts_sorted).to_csv(C_shift_save_path, index=False)
pd.DataFrame(error_j_total_results).to_csv(error_j_save_path, index=False)
pd.DataFrame(error_shift_H_total_results).to_csv(error_shift_H_save_path, index=False)
pd.DataFrame(error_shift_C_total_results).to_csv(error_shift_C_save_path, index=False)

# 存储为 parquet 文件
final_df.to_parquet(new_chunk_save_path, index=False)

print(f"new_chunk_total_results.shape: {final_df.shape}")




"""
in this step, we applied rules:
1, in 1H NMR, if the multiplet need j but no j was found, then drop the row
2, if solvent is DMSO-d6 or DMF-D7, and the atom number is not equal to the atom number in the abstract, then we need to delete the molecule
3, in 13C NMR, if the multiplet need j but no j was found, then drop the row
"""

import pandas as pd
import ast
from collections import Counter
import json
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
from rdkit import Chem

parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0715_final_1_fix_cd3socd3.parquet"

df = pd.read_parquet(parquet_path)

print(df.shape)

# H coupling range 0-30
# H shift range
# C shift range


allowed_elements = {"H", "C", "O", "N", "S", "Cl", "Br", "I"}

def is_valid_smiles(smiles, allowed_elements):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        elements_in_mol = {atom.GetSymbol() for atom in mol.GetAtoms()}
        return elements_in_mol.issubset(allowed_elements)
    except:
        return False

def process_chunk(chunk_df):
    chunk = chunk_df.copy()
    no_j_list = []
    err_H_num = []
    err_c_num = []
    for index, row in chunk.iterrows():

        if "H" in row["nmr_type"]:
            # 如果所有元素都在 allowed_elements 中，则继续
            line = ast.literal_eval(row["nmr_processed"])
            j_error = False
            h_num_error = False
            for i in line:
                if isinstance(i, str):
                    i = ast.literal_eval(i)
                if not isinstance(i, tuple):
                    continue
                if len(i) < 5:
                    continue
                
                if i[0] == 'd' or i[0] == 't' or i[0] == 'q' or i[0] == 'dd' or i[0] == 'dt':
                    j_list = i[1]
                    if str(j_list) == '[]':
                        j_error = True
            
            if row["nmr_solvent"] == 'DMSO-d6' or row["nmr_solvent"] == 'DMF-D7':
                if int(row["atom_number_abstract"]) != int(row["atom_number"]) and int(row["atom_number_abstract"]) != int(row["atom_number_diff_env"]):
                    h_num_error = True

            if j_error:
                no_j_list.append(row)
                chunk = chunk.drop(index, errors='ignore')
            if h_num_error:
                err_H_num.append(row)
        
        elif "C" in row["nmr_type"]:
            line = ast.literal_eval(row["nmr_processed"])
            j_error = False
            c_num_error = False
            for i in line:
                if isinstance(i, str):
                    i = ast.literal_eval(i)
                if not isinstance(i, tuple):
                    continue
                if len(i) < 3:
                    continue
                if i[1] == 'd' or i[1] == 't' or i[1] == 'q' or i[1] == 'dd' or i[1] == 'dt':
                    if str(i[2]) == 'None':
                        j_error = True
            # if int(row["atom_number_abstract"]) != int(row["atom_number"]) and int(row["atom_number_abstract"]) != int(row["atom_number_diff_env"]) and int(row["atom_number_abstract"]) < 4:
            if int(row["atom_number_abstract"]) < (int(row["atom_number_diff_env"])-1) and int(row["atom_number_abstract"]) < (int(row["atom_number"])/2):
                c_num_error = True
            
            if j_error:
                no_j_list.append(row)
                chunk = chunk.drop(index, errors='ignore')
            if c_num_error:
                err_c_num.append(row)
                chunk = chunk.drop(index, errors='ignore')

    return no_j_list, err_H_num, err_c_num, chunk

# 将 DataFrame 切块
chunk_size = 5000

chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

no_j_results = []
err_H_num_results = []
err_c_num_results = []

new_chunk_total_results = []

from multiprocessing import Pool
from tqdm import tqdm

with Pool(processes=60) as pool:
    for res in tqdm(pool.imap_unordered(process_chunk, chunks), total=len(chunks)):
        no_j_chunk, err_H_num_chunk, err_c_num_chunk, new_chunk = res

        no_j_results.extend(no_j_chunk)
        err_H_num_results.extend(err_H_num_chunk)
        err_c_num_results.extend(err_c_num_chunk)

        if isinstance(new_chunk, pd.DataFrame):
            new_chunk_total_results.append(new_chunk)
        else:
            print(f"[警告] 非DataFrame类型跳过: {type(new_chunk)}")

no_j_save_path = parquet_path.replace("fix_cd3socd3.parquet", "no_j.csv")
err_H_num_save_path = parquet_path.replace("fix_cd3socd3.parquet", "err_H_num.csv")
err_c_num_save_path = parquet_path.replace("fix_cd3socd3.parquet", "err_c_num_2.csv")

# 合并所有 DataFrame
final_df = pd.concat(new_chunk_total_results, ignore_index=True)

pd.DataFrame(no_j_results).to_csv(no_j_save_path, index=False)
pd.DataFrame(err_H_num_results).to_csv(err_H_num_save_path, index=False)
pd.DataFrame(err_c_num_results).to_csv(err_c_num_save_path, index=False)

new_chunk_save_path = parquet_path.replace("_0715_final_1_fix_cd3socd3.parquet", "_0716_1.parquet")

# 存储为 parquet 文件
final_df.to_parquet(new_chunk_save_path, index=False)

print(f"new_chunk_total_results.shape: {final_df.shape}")

# 路径设置
parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0716_1.parquet"
csv_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0715_final_1_err_H_num.csv"

# 读取数据
df_full = pd.read_parquet(parquet_path)
df_to_remove = pd.read_csv(csv_path)

# 为了确保比较一致，删除前先去除两列中的空格并统一为字符串
df_full['filename'] = df_full['filename'].astype(str).str.strip()
df_full['smiles'] = df_full['smiles'].astype(str).str.strip()
df_to_remove['filename'] = df_to_remove['filename'].astype(str).str.strip()
df_to_remove['smiles'] = df_to_remove['smiles'].astype(str).str.strip()

# 合并两个字段作为唯一标识
df_full['key'] = df_full['filename'] + '||' + df_full['smiles']
df_to_remove['key'] = df_to_remove['filename'] + '||' + df_to_remove['smiles']

# 构造要保留的掩码
mask_keep = ~df_full['key'].isin(set(df_to_remove['key']))

# 过滤并删除
df_filtered = df_full[mask_keep].drop(columns=['key'])

# 删除 merge_key 这一列
df_filtered = df_filtered.drop(columns=['merge_key'])

# 保存结果
output_path = parquet_path.replace(".parquet", "_final.parquet")
df_filtered.to_parquet(output_path, index=False)

print(f"删除完成，保留 {len(df_filtered)} 行，结果已保存至：{output_path}")

print(df_filtered.head())
print(df_filtered.shape)



# 读取 parquet 文件
parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0716_1_final.parquet"
df = pd.read_parquet(parquet_path)

# 替换不含 'mhz'（不区分大小写）的行的 nmr_frequency 为 'not_known'
df['nmr_frequency'] = df['nmr_frequency'].apply(
    lambda x: x if isinstance(x, str) and 'mhz' in x.lower() else 'not_known'
)

# 可选：保存结果到新文件
output_path = parquet_path.replace('.parquet', '_fix_freq.parquet')
df.to_parquet(output_path, index=False)

print(f"修改完成，结果保存到 {output_path}")
print(df.head())
print(df.shape)

df_sample1000 = df.sample(n=1000)

df_sample1000.to_csv("/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0716_1_final_sample1000.csv", index=False)








"""
Remove potential 13C NMR records with incorrect number of peaks.
"""

parquet_path = "/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0716_final_4.parquet"


df = pd.read_parquet(parquet_path)

print(df.shape)

# 统计 nmr_type 列中每种类型及出现次数
type_counts = df['smiles'].value_counts(dropna=False)

# 打印结果
print("smiles 总种类数:", type_counts.shape)
print(type_counts)

allowed_elements = {"H", "C", "O", "N", "S", "Cl", "Br", "I", "F", "P", "Si"}

def is_valid_smiles(smiles, allowed_elements):
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        elements_in_mol = {atom.GetSymbol() for atom in mol.GetAtoms()}
        return elements_in_mol.issubset(allowed_elements)
    except:
        return False

def process_chunk(chunk_df):
    chunk = chunk_df.copy()
    error_num_c_list = []

    for index, row in chunk.iterrows():
        need_filter = False
        if not is_valid_smiles(row["smiles"], allowed_elements):
            continue
        
        if "C" in row['nmr_type']:

            # 判断c_shift_list中是否存在重复的元素
            if row["atom_number_abstract"] < (row["atom_number_diff_env"]-1) and "CCCC" not in row["smiles"] and row["atom_number"] < 20:
                error_num_c_list.append(row)
                need_filter = True
        
        if need_filter:
            chunk = chunk.drop(index, errors='ignore')

    return error_num_c_list, chunk

# 将 DataFrame 切块
chunk_size = 5000

chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]


err_num_results = []

final_chunk_results = []

from multiprocessing import Pool
from tqdm import tqdm

with Pool(processes=60) as pool:
    for res in tqdm(pool.imap_unordered(process_chunk, chunks), total=len(chunks)):
        err_num_chunk, final_chunk = res

        err_num_results.extend(err_num_chunk)

        if isinstance(final_chunk, pd.DataFrame):
            final_chunk_results.append(final_chunk)
        else:
            print(f"[警告] 非DataFrame类型跳过: {type(final_chunk)}")

err_num_save_path = parquet_path.replace(".parquet", "err_num_0716_c_less_than_diff_env.csv")

# # 合并所有 DataFrame
final_df = pd.concat(final_chunk_results, ignore_index=True)

pd.DataFrame(err_num_results).to_csv(err_num_save_path, index=False)

new_chunk_save_path = parquet_path.replace("_final_3.parquet", "_final_4.parquet")

# 存储为 parquet 文件
final_df.to_parquet(new_chunk_save_path, index=False)

print(f"new_chunk_total_results.shape: {final_df.shape}")

final_df_sample_300 = final_df.sample(n=300)

final_df_sample_300.to_csv("/internfs/wangjunjie/nmr_si/nmr_result_all_0716/processed_results_0716_final_4_sample300.csv", index=False)

print(final_df_sample_300.shape)







