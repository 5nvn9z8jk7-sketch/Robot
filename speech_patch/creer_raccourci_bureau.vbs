' creer_raccourci_bureau.vbs - cree le raccourci Robot sur le Bureau
' (icone robot.ico, lance start_interface.bat). Sans PowerShell.
Option Explicit
Dim sh, fso, dossier, bureau, lnk
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dossier = fso.GetParentFolderName(WScript.ScriptFullName)
bureau = sh.SpecialFolders("Desktop")
Set lnk = sh.CreateShortcut(bureau & "\Robot.lnk")
lnk.TargetPath = dossier & "\start_interface.bat"
lnk.WorkingDirectory = dossier
lnk.IconLocation = dossier & "\robot.ico,0"
lnk.Description = "Interface de commande du robot ROSOrin"
lnk.Save
WScript.Echo "Raccourci cree : " & bureau & "\Robot.lnk"
