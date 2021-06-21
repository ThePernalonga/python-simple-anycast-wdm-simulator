import xml.dom.minidom as xt

doc = xt.parse("test.xml")

nos = doc.getElementsByTagName("status")

for numero in nos:
    x = numero.find("status").text
    print(x)
