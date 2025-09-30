import os
from typing import List, Dict, Any, Union, Tuple
import sys
import json
import re
import copy
from datetime import datetime
from io import StringIO
from pathlib import Path
from loguru import logger
from mineru.utils.pdf_image_tools import images_bytes_to_pdf_bytes

# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# sys.path.append(PROJECT_ROOT)

from app.utils.minio_client import minio_client, MINIO_BUCKET
from app.models.parsed_content import ParsedContent
from app.models.file import File as FileModel, FileStatus
from sqlalchemy.orm import Session
from mineru.data.data_reader_writer import DataWriter
from mineru.data.data_reader_writer.s3 import S3DataWriter
from mineru.utils.config_reader import get_s3_config, read_config
from mineru.cli.common import convert_pdf_bytes_to_bytes_by_pypdfium2
from mineru.utils.enum_class import MakeMode
from mineru.backend.vlm.vlm_analyze import doc_analyze as vlm_doc_analyze
from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make, \
    make_blocks_to_markdown
from mineru.backend.pipeline.model_json_to_middle_json import result_to_middle_json as pipeline_result_to_middle_json
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make
from mineru.backend.vlm.vlm_middle_json_mkcontent import mk_blocks_to_markdown
from app.models.settings import Settings
from app.utils.redis_client import redis_client

# 支持的文件扩展名
PDF_EXTENSIONS = [".pdf"]
# 2.0取消了liboffice套件，只支持pdf和图片
# OFFICE_EXTENSIONS = [".ppt", ".pptx", ".doc", ".docx"]
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"]

# Redis 频道名称
PARSER_CHANNEL = "file_parser_tasks"
PARSER_STREAM = "file_parser_stream"  # 统一使用这个名称
CONSUMER_GROUP = "parser_workers"

SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:30000")

class MemoryDataWriter(DataWriter):
    """内存数据写入器，用于临时存储解析结果"""

    def __init__(self):
        self.buffer = StringIO()

    def write(self, path: str, data: bytes) -> None:
        if isinstance(data, str):
            self.buffer.write(data)
        else:
            self.buffer.write(data.decode("utf-8"))

    def write_string(self, path: str, data: str) -> None:
        self.buffer.write(data)

    def get_value(self) -> str:
        return self.buffer.getvalue()

    def close(self):
        self.buffer.close()


def get_s3_image_url(image_path: str, bucket: str) -> str:
    """Get HTTP accessible image URL from S3"""
    # 获取S3配置
    _, _, endpoint = get_s3_config(bucket)

    # 直接使用endpoint和image_path构建URL
    return f"{endpoint}/{bucket}/{image_path}"


def modify_markdown_image_urls(markdown_content: str, bucket: str) -> str:
    """修改Markdown内容中的图片URL为S3 HTTP URL"""
    # 匹配Markdown中的图片标签
    pattern = r'\!\[(?:[^\]]*)\]\(([^)]+)\)'

    def replace_url(match):
        image_path = match.group(1)
        # 如果已经是完整的URL，则跳过
        if image_path.startswith(('http://', 'https://')):
            return match.group(0)
        # 否则转换为S3 URL
        print(image_path, '---')
        return f'![]({get_s3_image_url(image_path, bucket)})'

    # 应用替换
    return re.sub(pattern, replace_url, markdown_content)


def get_buckets() -> list[str]:
    """获取默认bucket"""
    config = read_config()
    bucket_info = config.get('bucket_info', {})
    if not bucket_info:
        raise Exception('未找到bucket配置信息')
    # 默认[images, mds],分别存储图片和解析后的markdown文件
    return list(bucket_info.keys())




class ParserService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def do_parse(
            pdf_file_names: list[str],  # List of PDF file names to be parsed
            pdf_bytes_list: list[bytes],  # List of PDF bytes to be parsed
            p_lang_list: list[str],  # List of languages for each PDF, default is 'ch' (Chinese)
            backend="pipeline",  # The backend for parsing PDF, default is 'pipeline'
            parse_method="auto",  # The method for parsing PDF, default is 'auto'
            p_formula_enable=True,  # Enable formula parsing
            p_table_enable=True,  # Enable table parsing
            server_url=None,  # Server URL for vlm-http-client backend
            f_dump_md=True,  # Whether to dump markdown files
            f_dump_middle_json=True,  # Whether to dump middle JSON files
            f_dump_model_output=True,  # Whether to dump model output files
            f_dump_content_list=False,  # Whether to dump content list files
            f_make_md_mode=MakeMode.MM_MD,  # The mode for making markdown content, default is MM_MD
            start_page_id=0,  # Start page ID for parsing, default is 0
            end_page_id=None,
            # End page ID for parsing, default is None (parse all pages until the end of the document)
            md_writer=None,
            image_writer=None,
            mds_bucket="mds",  # 默认存储的bucket
            predictor=None,  # 可以预加载vlm模型传入
    ):
        md_content_list = []
        if backend == "pipeline":
            for idx, pdf_bytes in enumerate(pdf_bytes_list):
                new_pdf_bytes = convert_pdf_bytes_to_bytes_by_pypdfium2(pdf_bytes, start_page_id, end_page_id)
                pdf_bytes_list[idx] = new_pdf_bytes

            infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
                pdf_bytes_list,
                p_lang_list,
                parse_method=parse_method,
                formula_enable=p_formula_enable,
                table_enable=p_table_enable)

            for idx, model_list in enumerate(infer_results):
                model_json = copy.deepcopy(model_list)
                pdf_file_name = pdf_file_names[idx]

                images_list = all_image_lists[idx]
                pdf_doc = all_pdf_docs[idx]
                _lang = lang_list[idx]
                _ocr_enable = ocr_enabled_list[idx]
                middle_json = pipeline_result_to_middle_json(model_list, images_list, pdf_doc, image_writer, _lang,
                                                             _ocr_enable, p_formula_enable)
                pdf_info = middle_json["pdf_info"]

                if f_dump_md:
                    md_content_str = pipeline_union_make(pdf_info, f_make_md_mode, "images")
                    md_content_str = modify_markdown_image_urls(md_content_str, mds_bucket)
                    md_content_list.append(md_content_str)
                    md_writer.write_string(
                        f"{pdf_file_name}.md",
                        md_content_str,
                    )
                    md_content_with_pages = ParserService.convert_middle_json_to_markdown(middle_json, keep_page=True, backend=backend)
                    md_content_with_pages = modify_markdown_image_urls(md_content_with_pages, mds_bucket)
                    md_writer.write_string(
                        f"{pdf_file_name}_pages.md",
                        md_content_with_pages,
                    )

                if f_dump_content_list:
                    content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, "images")
                    md_writer.write_string(
                        f"{pdf_file_name}_content_list.json",
                        json.dumps(content_list, ensure_ascii=False, indent=4),
                    )

                if f_dump_middle_json:
                    md_writer.write_string(
                        f"{pdf_file_name}_middle.json",
                        json.dumps(middle_json, ensure_ascii=False, indent=4),
                    )

                if f_dump_model_output:
                    md_writer.write_string(
                        f"{pdf_file_name}_model.json",
                        json.dumps(model_json, ensure_ascii=False, indent=4),
                    )

        else:
            if backend.startswith("vlm-"):
                backend = backend[4:]
            conf = read_config()
            model_path = conf.get("models-dir", {}).get("vlm", '')
            for idx, pdf_bytes in enumerate(pdf_bytes_list):
                pdf_file_name = pdf_file_names[idx]
                pdf_bytes = convert_pdf_bytes_to_bytes_by_pypdfium2(pdf_bytes, start_page_id, end_page_id)
                middle_json, infer_result = vlm_doc_analyze(pdf_bytes, image_writer=image_writer, predictor=predictor, backend=backend,
                                                             model_path=model_path, server_url=server_url)
                pdf_info = middle_json["pdf_info"]

                if f_dump_md:
                    md_content_str = vlm_union_make(pdf_info, f_make_md_mode, "images")
                    md_content_str = modify_markdown_image_urls(md_content_str, mds_bucket)
                    md_content_list.append(md_content_str)
                    md_writer.write_string(
                        f"{pdf_file_name}.md",
                        md_content_str,
                    )
                    md_content_with_pages = ParserService.convert_middle_json_to_markdown(middle_json, keep_page=True, p_formula_enable=p_formula_enable, p_table_enable=p_table_enable, backend=backend)
                    md_content_with_pages = modify_markdown_image_urls(md_content_with_pages, mds_bucket)
                    md_writer.write_string(
                        f"{pdf_file_name}_pages.md",
                        md_content_with_pages,
                    )

                if f_dump_content_list:
                    content_list = vlm_union_make(pdf_info, MakeMode.CONTENT_LIST, "images")
                    md_writer.write_string(
                        f"{pdf_file_name}_content_list.json",
                        json.dumps(content_list, ensure_ascii=False, indent=4),
                    )

                if f_dump_middle_json:
                    md_writer.write_string(
                        f"{pdf_file_name}_middle.json",
                        json.dumps(middle_json, ensure_ascii=False, indent=4),
                    )

                if f_dump_model_output:
                    md_writer.write_string(
                        f"{pdf_file_name}_model.json",
                        json.dumps(infer_result, ensure_ascii=False, indent=4),
                    )
        return md_content_list

    @staticmethod
    def convert_middle_json_to_markdown(middle_json: Dict[str, Any], keep_page: bool = True, p_formula_enable=True, p_table_enable=True, backend='pipeline') -> str:
        """将 middle_json 转换为 markdown 格式
        Args:
            middle_json: 中间 JSON 数据
            keep_page: 是否保留页码信息
        Returns:
            str: 转换后的 markdown 内容
        """
        pdf_info_dict = middle_json.get('pdf_info', [])
        output_content = []
        for page_info in pdf_info_dict:
            paras_of_layout = page_info.get('para_blocks')
            page_idx = page_info.get('page_idx')
            if not paras_of_layout:
                continue
            if backend == 'pipeline':
                page_markdown = make_blocks_to_markdown(paras_of_layout, MakeMode.MM_MD, "images")
            else:
                page_markdown = mk_blocks_to_markdown(paras_of_layout, MakeMode.MM_MD, p_formula_enable, p_table_enable, "images")
            if keep_page:
                output_content.append(f"{{{page_idx}}}{'-' * 48}")
            output_content.extend(page_markdown)
        return '\n\n'.join(output_content)

    def process_file(
            self,
            file_name: str,
            file_bytes: bytes,
            file_extension: str,
            parse_method: str,
            lang: str,
            formula_enable: bool,
            table_enable: bool,
            image_writer: DataWriter,
            md_writer: DataWriter,
            backend: str,
            server_url: str,
            mds_bucket: str,
            predictor,
    ):
        """处理文件内容
        Args:
            file_name: 文件名 stem
            file_bytes: 文件字节内容
            file_extension: 文件扩展名
            parse_method: 解析方法 (auto, ocr, txt)
            lang: 语言
            formula_enable: 是否启用公式识别
            table_enable: 是否启用表格识别
            image_writer: 图片写入器
            md_writer: markdown写入器
            backend: 解析后端
            server_url: 当backend是 `vllm-client`时候, 需指定, 例如:`http://127.0.0.1:30000`
            mds_bucket: md存储桶
            predictor: vlm模型
        """

        try:
            # 检查文件类型是否支持
            if file_extension not in PDF_EXTENSIONS + IMAGE_EXTENSIONS:
                raise ValueError(f"不支持的文件类型: {file_extension}")
            file_name_list = [file_name]
            if file_extension in IMAGE_EXTENSIONS:
                pdf_bytes = images_bytes_to_pdf_bytes(file_bytes)
            else:
                pdf_bytes = file_bytes
            pdf_bytes_list = [pdf_bytes]
            lang_list = [lang]

            return self.do_parse(
                pdf_file_names=file_name_list,
                pdf_bytes_list=pdf_bytes_list,
                p_lang_list=lang_list,
                p_formula_enable=formula_enable,
                p_table_enable=table_enable,
                backend=backend,
                parse_method=parse_method,
                server_url=server_url,
                md_writer=md_writer,
                image_writer=image_writer,
                mds_bucket=mds_bucket,
                predictor=predictor
            )
        except Exception as e:
            logger.exception(f"处理文件失败: {str(e)}")
            raise

    def parse_file(self, file: FileModel, user_id: str, parse_method: str = "auto", predictor=None) -> Dict[str, Any]:
        """同步解析文件"""
        try:
            # 获取用户设置，如果没有则使用默认配置
            user_settings = self.db.query(Settings).filter(Settings.user_id == user_id).first()
            if not user_settings:
                user_settings = Settings(
                    user_id=user_id,
                    force_ocr=False,
                    ocr_lang='ch',
                    formula_recognition=True,
                    table_recognition=True
                )
            settings = user_settings.to_dict()
            logger.info(settings)
            if settings.get('force_ocr', False):
                parse_method = 'ocr'
            # backend做成配置
            backend = settings.get("backend", "pipeline")
            # 更新文件状态为解析中
            file.status = FileStatus.PARSING
            file.start_at = datetime.now()
            self.db.commit()

            # 从MinIO获取文件
            response = minio_client.get_object(MINIO_BUCKET, file.minio_path)
            file_bytes = response.read()
            file_extension = Path(file.minio_path).suffix.lower()
            file_name = Path(file.minio_path).name
            file_name_stem = Path(file_name).stem
            # 获取默认bucket配置
            buckets = get_buckets()
            # 默认读取第一个bucket配置存储生成的markdown，保持output.md和images文件夹在同级目录
            mds_bucket = buckets[0]
            if not minio_client.bucket_exists(mds_bucket):
                minio_client.make_bucket(mds_bucket)
            ak, sk, endpoint = get_s3_config(mds_bucket)
            # TODO 增加本地文件夹存储选配
            md_content_writer_s3 = S3DataWriter(
                "",
                bucket=mds_bucket,
                ak=ak,
                sk=sk,
                endpoint_url=endpoint
            )
            # 创建S3写入器用于图片
            image_writer = S3DataWriter(
                "images",  # 图片存储在images目录下
                bucket=mds_bucket,
                ak=ak,
                sk=sk,
                endpoint_url=endpoint
            )

            try:
                # 处理文件
                md_content_list = self.process_file(
                    file_name_stem,
                    file_bytes,
                    file_extension,
                    parse_method,
                    settings.get('ocr_lang', 'ch'),
                    settings.get('formula_recognition', True),
                    settings.get('table_recognition', True),
                    image_writer,
                    md_content_writer_s3,
                    backend=backend,
                    server_url=SERVER_URL,
                    mds_bucket=mds_bucket,
                    predictor=predictor
                )
                # 保存解析结果到数据库
                parsed_content = ParsedContent(
                    user_id=user_id,
                    file_id=file.id,
                    content=md_content_list[0]
                )
                self.db.add(parsed_content)

                # 更新文件状态为已解析
                file.status = FileStatus.PARSED
                file.finish_at = datetime.now()
                self.db.commit()

                return {
                    "status": "success"
                }

            finally:
                pass

        except Exception as e:
            # 发生错误时回滚并更新状态
            self.db.rollback()
            file.status = FileStatus.PARSE_FAILED
            self.db.commit()
            raise Exception(f"解析失败: {str(e)}")

    def get_parsed_content(self, file_id: int, user_id: str):
        """获取已解析的内容"""
        query = self.db.query(ParsedContent).filter(
            ParsedContent.file_id == file_id,
            ParsedContent.user_id == user_id
        )

        content_obj = query.first()

        return content_obj.content if content_obj else ""

    def queue_parse_file(self, file: FileModel, user_id: str, parse_method: str = "auto") -> Dict[str, Any]:
        """
        将文件解析任务发布到 Redis Stream
        Args:
            file (FileModel): 文件模型实例
            user_id (str): 用户ID
            parse_method (str): 解析方法，可选值：auto, ocr, txt
        Returns:
            Dict[str, Any]: 包含任务状态的字典
        """
        try:
            # 更新文件状态为等待解析
            file.status = FileStatus.PENDING
            self.db.commit()

            # 准备任务数据
            task_data = {
                "file_id": file.id,
                "user_id": user_id,
                "parse_method": parse_method
            }

            # 发布任务到 Redis Stream
            logger.info(f"Publishing task to stream {PARSER_STREAM}: {task_data}")
            redis_client.publish_task(PARSER_STREAM, task_data)

            return {
                "status": "queued",
                "message": "File parsing task has been queued",
                "file_id": file.id
            }

        except Exception as e:
            # 发生错误时回滚并更新状态
            self.db.rollback()
            file.status = FileStatus.PARSE_FAILED
            self.db.commit()
            raise Exception(f"Failed to queue parsing task: {str(e)}")


if __name__ == "__main__":
    test_file = '/home/lpdswing/projects/mineru-web/images/preview.png'
    with open(test_file, 'rb') as f:
        file_bytes = f.read()

    ParserService.do_parse(
        ['preview.png'],
        [file_bytes],
        p_lang_list=['ch'],

    )
