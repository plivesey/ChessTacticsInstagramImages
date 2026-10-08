import zipfile
z = zipfile.ZipFile("games/twic/twic1665g.zip")
z.extractall("games/twic")
print(z.namelist())
