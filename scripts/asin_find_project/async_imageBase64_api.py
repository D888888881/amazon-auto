import asyncio
import base64
import json
from PIL import Image
from io import BytesIO

def _convert_sync(image_path, quality=92, bg_color=(255, 255, 255)):
    """
    同步执行图片转换的核心逻辑（保持原函数逻辑）
    """
    # 1. 打开图片（此处简化，只处理本地文件）
    img = Image.open(image_path)

    # 2. 处理透明通道
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, bg_color)
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # 3. 保存为 JPEG 到内存
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=quality)
    jpeg_bytes = buffer.getvalue()

    # 4. 转换为 Base64
    base64_str = base64.b64encode(jpeg_bytes).decode('utf-8')
    result = {
        'imageBase64': f"data:image/jpeg;base64,{base64_str}",
        'bizType': 'selectionTool',
        'language': 'zh'
    }
    return json.dumps(result, ensure_ascii=False, indent=2)

async def convert_to_jpeg_base64_async(image_path, quality=92, bg_color=(255, 255, 255)):
    """
    异步版本的图片转换函数
    """
    # 使用 asyncio.to_thread 将同步阻塞操作放到线程池中执行
    return await asyncio.to_thread(_convert_sync, image_path, quality, bg_color)

# 使用示例
async def main():
    # 异步执行转换
    jpeg_json = await convert_to_jpeg_base64_async("images/图片2.jpeg")
    print(jpeg_json)

# 运行异步主函数
if __name__ == "__main__":
    asyncio.run(main())