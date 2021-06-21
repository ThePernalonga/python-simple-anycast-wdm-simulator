import xml.etree.ElementTree as ET
tree = ET.parse('test.xml')
root = tree.getroot()

# all items data
print('Data:')

for elem in root.findall(""):
  
    for subelem in elem:
      print(subelem.value)

""""
import xml.etree.ElementTree as ET
tree = ET.parse('your_file.xml')
root = tree.getroot()

for group in root.findall('group'):
  title = group.find('title')
  titlephrase = title.find('phrase').text
  for doc in group.findall('document'):
    refid = doc.get('refid')
"""

for group in root.findall('group'):
  title = group.find('title')
  titlephrase = title.find('phrase').text
  for doc in group.findall('document'):
    refid = doc.get('refid')