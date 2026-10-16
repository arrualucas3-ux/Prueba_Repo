"""Launch UE 5.6 locally, cook assets, and produce a filtered ZIP for final packing."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'Ride/Ride.uproject'
LOGS = ROOT / 'Logs'
MESH = Path('Ride/Content/Mods/Jinx/SK_Jinx_RV.uasset')
ALLOWED_EXTENSIONS = {'.uasset', '.uexp', '.ubulk', '.uptnl'}


def check_engine(engine):
    engine = Path(engine).expanduser().resolve()
    version = json.loads((engine / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version.get('MajorVersion'), version.get('MinorVersion')) != (5, 6):
        raise RuntimeError('Se necesita Unreal Engine 5.6.x. No usar otra version.')
    editor = engine / 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    if not editor.is_file():
        raise RuntimeError('No se encontro UnrealEditor-Cmd.exe para Windows.')
    return editor, version


def run_editor(editor, arguments, log_name):
    log = LOGS / log_name
    command = [str(editor), str(PROJECT), *arguments, '-unattended', '-nosplash',
               '-nosound', '-NullRHI', '-stdout', '-FullStdOutLogOutput', '-UTF8Output',
               '-abslog=' + str(LOGS / (Path(log_name).stem + '_Engine.log'))]
    print('Procesando. Registro: ' + str(log), flush=True)
    # Write directly to disk: avoid retaining potentially large shader logs in RAM.
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
                                check=False)
    if result.returncode:
        raise RuntimeError('Unreal termino con error %s. Enviar Logs/%s.' % (result.returncode, log_name))


def select_cooked_files(cooked):
    """Include this mod's new mesh, materials and textures, excluding placeholders."""
    cooked = Path(cooked).resolve()
    expected = cooked / MESH
    if not expected.is_file():
        raise RuntimeError('No se encontro la malla cocinada: ' + str(expected))
    selected = []
    for path in sorted((cooked / 'Ride/Content').rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        relative = path.relative_to(cooked)
        parts = relative.parts
        is_jinx = parts[:4] == ('Ride', 'Content', 'Mods', 'Jinx')
        is_mesh = relative.parent == MESH.parent and path.stem == MESH.stem
        if is_jinx or is_mesh:
            if path.is_symlink() or not path.resolve().is_relative_to(cooked):
                raise RuntimeError('Ruta de recurso inesperada: ' + str(path))
            selected.append((path, relative))
    if not any(r.parts[:5] == ('Ride', 'Content', 'Mods', 'Jinx', 'Materials') for _, r in selected):
        raise RuntimeError('No se encontraron materiales cocinados de Jinx.')
    if not any(r.parts[:5] == ('Ride', 'Content', 'Mods', 'Jinx', 'Textures') for _, r in selected):
        raise RuntimeError('No se encontraron texturas cocinadas de Jinx.')
    return selected


def zip_cooked(cooked, output):
    selected = select_cooked_files(cooked)
    entries = [{'path': str(relative).replace('\\', '/'), 'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path, relative in selected]
    report = {'status': 'cooked_unpacked', 'engine': '5.6', 'tested_in_game': False,
              'files': entries,
              'excluded_game_packages': ['SK_BoxyRider_01_Skeleton', 'SK_BoxyRider_01_Physics_Ragdoll'],
              'runtime_prototype': 'Jinx_Adaptada_RV; local existing pawn, third-person body',
              'next_step': 'Convert legacy cooked assets to IoStore with UE5_6 support, verify containers, and test the UE4SS prototype in game.'}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix('.zip.partial')
    if partial.exists():
        partial.unlink()
    try:
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
            for path, relative in selected:
                archive.write(path, str(relative).replace('\\', '/'))
            archive.writestr('Informe_Cocinado.json', json.dumps(report, indent=2))
            if (LOGS / 'Importacion.json').is_file():
                archive.write(LOGS / 'Importacion.json', 'Informes/Importacion.json')
            runtime = ROOT / 'Prototipo_UE4SS/Mods/Jinx_Adaptada_RV/Scripts'
            for filename in ('main.lua', 'JinxRuntimeAssets.lua'):
                script = runtime / filename
                if not script.is_file():
                    raise RuntimeError('Falta el controlador UE4SS: ' + filename)
                archive.write(script, 'Controlador_UE4SS/Mods/Jinx_Adaptada_RV/Scripts/' + filename)
            archive.writestr('Controlador_UE4SS/Mods/Jinx_Adaptada_RV/enabled.txt', '')
        with zipfile.ZipFile(partial) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('El ZIP cocinado no paso la comprobacion de integridad.')
        os.replace(partial, output)
    finally:
        if partial.exists():
            partial.unlink()
    return report


def main():
    if len(sys.argv) != 2:
        raise RuntimeError('Indicar la carpeta de Unreal Engine 5.6.')
    LOGS.mkdir(parents=True, exist_ok=True)
    editor, version = check_engine(sys.argv[1])
    print('Unreal Engine %d.%d.%d. Preparando Jinx.' %
          (version['MajorVersion'], version['MinorVersion'], version.get('PatchVersion', 0)), flush=True)
    import_report = LOGS / 'Importacion.json'
    if import_report.exists():
        import_report.unlink()
    run_editor(editor, ['-run=pythonscript', '-script=' + str(ROOT / 'Tools/import_jinx.py')], '01_Importacion.log')
    if not import_report.is_file():
        raise RuntimeError('Unreal no ejecuto la importacion. Enviar Logs/01_Importacion.log.')
    imported = json.loads(import_report.read_text(encoding='utf-8'))
    if imported.get('status') != 'imported_and_verified':
        raise RuntimeError('La importacion no paso la validacion. Enviar Logs/Importacion.json.')
    print('Malla y materiales importados. Cocinando para Windows; puede tardar varios minutos.', flush=True)
    run_editor(editor, ['-run=cook', '-targetplatform=Windows', '-cookall', '-unversioned',
                        '-SkipEditorContent', '-NoDefaultMaps', '-NoGameAlwaysCook'], '02_Cocinado.log')
    candidates = [ROOT / 'Ride/Saved/Cooked/Windows', ROOT / 'Ride/Saved/Cooked/WindowsNoEditor',
                  ROOT / 'Ride/Saved/Sandboxes/Cooked-Windows', ROOT / 'Ride/Saved/Sandboxes/Cooked-WindowsNoEditor']
    cooked = next((p for p in candidates if (p / MESH).is_file()), None)
    if cooked is None:
        raise RuntimeError('No aparecieron los archivos cocinados. Enviar Logs/02_Cocinado.log.')
    output = ROOT / 'Resultado/Cocinados_Jinx_RV.zip'
    report = zip_cooked(cooked, output)
    print('\nTERMINADO: ' + str(output), flush=True)
    print('Recursos cocinados: %d. Subir este ZIP al chat para empaquetar el mod.' % len(report['files']), flush=True)
    print('Este ZIP todavia no se copia en Paks. Falta el empaquetado IoStore y la prueba en el juego.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\nERROR: ' + str(error), file=sys.stderr, flush=True)
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / 'Error_Preparacion.txt').write_text(traceback.format_exc(), encoding='utf-8')
        sys.exit(1)
