import asyncio
import json
import aiofiles


async def read_config_async(file_path: str):
    """异步读取 config.json 文件并返回解析后的字典"""
    try:
        # 异步读取文件内容
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()

        # 解析 JSON（将同步操作放到线程池中，避免阻塞事件循环）
        data = await asyncio.to_thread(json.loads, content)
        return data
    except FileNotFoundError:
        print(f"文件 {file_path} 不存在")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        return None


# 使用示例
async def read_main(path: str):
    config = await read_config_async(path)
    try:
        return config
    except FileNotFoundError:
        print(f"<UNK> {config} <UNK>不存在")
        return None

async def read_taobao_config(path:str):
    config = await read_config_async(path)
    result = {}
    try:
        if config is None:
            return None
        for item in config:
             if item['name'] == '_m_h5_tk' or item['name'] == '_m_h5_tk_enc':
                 result[item['name']] = item['value']
        # print(result)
        return result
    except FileNotFoundError:
        print(f"<UNK> {config} <UNK>不存在")
        return None

if __name__ == "__main__":
     asyncio.run(read_taobao_config('config_file/taobao_cookies.json'))
