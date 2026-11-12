from PIL import Image

# 打开图片
img = Image.open('./assets/C盘清理工具图标__1_-removebg-preview.png') # 替换为你的文件名

# 获取原始尺寸
original_size = img.size 

# 保存为 ICO，并指定尺寸为原始尺寸
# 注意：Windows 系统通常最大显示 256x256 的图标，但文件本身可以包含更大分辨率
img.save('output_icon.ico', format='ICO',size=(1680,1680))
