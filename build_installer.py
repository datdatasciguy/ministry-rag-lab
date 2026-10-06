import argparse
import hashlib
import importlib.metadata
import platform
import shutil
import subprocess
import sys
from pathlib import Path

def build(version, compiler=None):
    root = Path(__file__).resolve().parent
    output = root / 'outputs/installer-build'
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed',
               '--name', 'Ministry Search RAG', '--distpath', str(output / 'dist'),
               '--workpath', str(output / 'work'), '--specpath', str(output),
               '--add-data', str(root / 'web') + ':web', '--add-data', str(root / 'LICENSE') + ':.',
               '--add-data', str(root / 'docs') + ':docs', '--collect-submodules', 'uvicorn',
               '--exclude-module', 'tkinter', '--exclude-module', 'pytest', '--noupx']
    if sys.platform == 'darwin':
        command += ['--osx-bundle-identifier', 'com.datdatasciguy.ministrysearchrag']
    subprocess.run(command + [str(root / 'launcher.py')], check=True, cwd=root)
    bundle = output / 'dist/Ministry Search RAG'
    resources = bundle / '_internal'
    if sys.platform == 'darwin':
        bundle = output / 'dist/Ministry Search RAG.app'
        resources = bundle / 'Contents/Resources'
    # Preserve runtime dependency license files inside the distributable
    licenses = resources / 'third_party_licenses'
    versions = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata['Name']
        versions.append(name + '==' + distribution.version)
        for file in distribution.files or []:
            if file.name.lower().startswith(('license', 'copying', 'notice')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = licenses / name / str(file).replace('..', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    licenses.mkdir(parents=True, exist_ok=True)
    (licenses / 'build-dependencies.txt').write_text('\n'.join(sorted(versions)) + '\n', encoding='utf-8')
    for name in ['LICENSE.txt', 'LICENSE']:
        source = Path(sys.base_prefix) / name
        if source.is_file():
            shutil.copyfile(source, licenses / 'Python-LICENSE.txt')
            break
    forbidden = [path for path in bundle.rglob('*') if path.is_file() and path.suffix.lower() in {'.sqlite', '.jsonl', '.pdb', '.npy', '.ipynb', '.gguf', '.safetensors'}]
    if forbidden:
        raise ValueError('Unexpected collection/model/diagnostic files in app bundle')
    if sys.platform == 'win32':
        compiler = compiler or shutil.which('iscc') or r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        subprocess.run([compiler, '/DAppVersion=' + version, '/DBundleDir=' + str(bundle),
                        '/DOutputDir=' + str(output), str(root / 'installer/windows.iss')], check=True)
        artifact = output / f'MinistrySearchRAG-{version}-windows-x64.exe'
    elif sys.platform == 'darwin':
        # Adding notices changes the app bundle, so refresh its ad-hoc signature
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(bundle)], check=True)
        stage = output / 'dmg-content'
        stage.mkdir(exist_ok=True)
        target = stage / bundle.name
        if target.exists():
            raise ValueError('Choose a fresh build directory before rebuilding the Mac disk image')
        shutil.copytree(bundle, target, symlinks=True)
        (stage / 'Applications').symlink_to('/Applications')
        artifact = output / f'MinistrySearchRAG-{version}-macos-{platform.machine()}.dmg'
        subprocess.run(['hdiutil', 'create', '-volname', 'Ministry Search RAG', '-srcfolder', str(stage),
                        '-ov', '-format', 'UDZO', str(artifact)], check=True)
    else:
        raise ValueError('Build installers on Windows or macOS')
    digest = hashlib.file_digest(artifact.open('rb'), 'sha256').hexdigest()
    artifact.with_suffix(artifact.suffix + '.sha256').write_text(digest + '  ' + artifact.name + '\n')
    print(artifact)
    return artifact

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bundle the runtime and build a code-only desktop installer.')
    parser.add_argument('--version', required=True)
    parser.add_argument('--compiler')
    args = parser.parse_args()
    build(args.version, args.compiler)
