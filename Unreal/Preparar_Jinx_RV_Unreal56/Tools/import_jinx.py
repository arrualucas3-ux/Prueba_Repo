"""Run inside Unreal Editor 5.6 with -run=pythonscript. No game files are modified."""
from pathlib import Path
import hashlib
import json
import math
import re
import traceback
import unreal

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'Source/import_manifest.json').read_text(encoding='utf-8'))
REPORT_FILE = ROOT / 'Logs/Importacion.json'
REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
REPORT = {'status': 'started', 'tested_in_game': False}


def canonical(name):
    return re.sub('[^a-z0-9]', '', str(name).lower())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def asset_import(source, folder, name, options=None, factory=None):
    task = unreal.AssetImportTask()
    task.set_editor_property('filename', str(source))
    task.set_editor_property('destination_path', folder)
    task.set_editor_property('destination_name', name)
    task.set_editor_property('automated', True)
    task.set_editor_property('replace_existing', True)
    task.set_editor_property('save', True)
    if options is not None:
        task.set_editor_property('options', options)
    if factory is not None:
        task.set_editor_property('factory', factory)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    assets = [unreal.EditorAssetLibrary.load_asset(p)
              for p in task.get_editor_property('imported_object_paths')]
    return [a for a in assets if a is not None]


def relocate(asset, destination):
    source = str(asset.get_path_name()).split('.')[0]
    if source != destination:
        require(not unreal.EditorAssetLibrary.does_asset_exist(destination),
                'Ya existe el destino inesperado: ' + destination)
        require(unreal.EditorAssetLibrary.rename_asset(source, destination),
                'No se pudo renombrar: ' + source)
        asset = unreal.EditorAssetLibrary.load_asset(destination)
    require(asset is not None, 'Recurso ausente: ' + destination)
    return asset


def verify_bones(mesh):
    component = unreal.SkeletalMeshComponent()
    component.set_skeletal_mesh_asset(mesh)
    names = [str(component.get_bone_name(i)) for i in range(component.get_num_bones())]
    expected = {b['name']: b for b in MANIFEST['bones']}
    require(set(names) == set(expected),
            'Huesos diferentes. Faltan: %s; sobran: %s' %
            (sorted(set(expected) - set(names)), sorted(set(names) - set(expected))))
    checks = []
    for index, name in enumerate(names):
        parent = str(component.get_parent_bone(name))
        parent = None if parent.lower() in ('none', '') else parent
        require(parent == expected[name]['parent'], 'Padre incorrecto: ' + name)
        transform = component.get_ref_pose_transform(index)
        t = transform.translation
        q = transform.rotation
        scale = transform.scale3d
        actual_t = [t.x, t.y, t.z]
        actual_q = [q.x, q.y, q.z, q.w]
        actual_s = [scale.x, scale.y, scale.z]
        distance = math.sqrt(sum((a-b)**2 for a, b in zip(actual_t, expected[name]['translation_cm'])))
        norm_a = math.sqrt(sum(x*x for x in actual_q))
        norm_b = math.sqrt(sum(x*x for x in expected[name]['rotation_xyzw']))
        require(norm_a > 0 and norm_b > 0, 'Rotacion nula: ' + name)
        dot = abs(sum(a*b for a, b in zip(actual_q, expected[name]['rotation_xyzw'])) / (norm_a*norm_b))
        angle = math.degrees(2*math.acos(min(1.0, dot)))
        scale_error = max(abs(a-b) for a, b in zip(actual_s, expected[name]['scale']))
        checks.append({'name': name, 'translation_cm': actual_t, 'rotation_xyzw': actual_q,
                       'scale': actual_s, 'position_error_cm': distance,
                       'rotation_error_degrees': angle, 'scale_error': scale_error})
    REPORT['bone_checks'] = checks
    REPORT['imported_bones'] = len(names)
    worst_position = max(c['position_error_cm'] for c in checks)
    worst_rotation = max(c['rotation_error_degrees'] for c in checks)
    worst_scale = max(c['scale_error'] for c in checks)
    REPORT['max_position_error_cm'] = worst_position
    REPORT['max_rotation_error_degrees'] = worst_rotation
    require(worst_position < 0.05 and worst_rotation < 0.2 and worst_scale < 0.001,
            'La importacion cambio el reposo. Posicion %.5f cm, rotacion %.5f grados. '
            'Enviar Logs/Importacion.json para corregirla antes del cocinado.' %
            (worst_position, worst_rotation))


def make_materials():
    result = {}
    textures = {}
    for definition in MANIFEST['materials']:
        for role, relative in definition['textures'].items():
            if relative in textures:
                continue
            source = ROOT / relative
            assets = asset_import(source, '/Game/Mods/Jinx/Textures', source.stem,
                                  factory=unreal.TextureFactory())
            texture = next((a for a in assets if isinstance(a, unreal.Texture2D)), None)
            require(texture is not None, 'No se importo la textura: ' + relative)
            texture.set_editor_property('srgb', role == 'base_color')
            if role == 'normal':
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
                texture.set_editor_property('flip_green_channel', True)
            elif role == 'metallic_roughness':
                texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
            require(unreal.EditorAssetLibrary.save_loaded_asset(texture),
                    'No se guardo la textura: ' + relative)
            textures[relative] = texture
        name = definition['asset_name']
        path = '/Game/Mods/Jinx/Materials/' + name
        material = unreal.EditorAssetLibrary.load_asset(path)
        if material is None:
            material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                name, '/Game/Mods/Jinx/Materials', unreal.Material, unreal.MaterialFactoryNew())
        require(isinstance(material, unreal.Material), 'Material invalido: ' + path)
        unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
        material.set_editor_property('two_sided', definition['two_sided'])
        unreal.MaterialEditingLibrary.set_material_usage(material, unreal.MaterialUsage.MATUSAGE_SKELETAL_MESH)
        for role, relative in definition['textures'].items():
            expression = unreal.MaterialEditingLibrary.create_material_expression(
                material, unreal.MaterialExpressionTextureSample, -400, 0)
            expression.set_editor_property('texture', textures[relative])
            sampler = (unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if role == 'normal'
                       else unreal.MaterialSamplerType.SAMPLERTYPE_MASKS if role == 'metallic_roughness'
                       else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
            expression.set_editor_property('sampler_type', sampler)
            if role == 'base_color':
                require(unreal.MaterialEditingLibrary.connect_material_property(
                    expression, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR), 'Conexion BaseColor fallida')
            elif role == 'normal':
                require(unreal.MaterialEditingLibrary.connect_material_property(
                    expression, 'RGB', unreal.MaterialProperty.MP_NORMAL), 'Conexion Normal fallida')
            else:
                require(unreal.MaterialEditingLibrary.connect_material_property(
                    expression, 'G', unreal.MaterialProperty.MP_ROUGHNESS), 'Conexion Roughness fallida')
                require(unreal.MaterialEditingLibrary.connect_material_property(
                    expression, 'B', unreal.MaterialProperty.MP_METALLIC), 'Conexion Metallic fallida')
        unreal.MaterialEditingLibrary.layout_material_expressions(material)
        unreal.MaterialEditingLibrary.recompile_material(material)
        require(unreal.EditorAssetLibrary.save_loaded_asset(material), 'No se guardo: ' + path)
        result[canonical(definition['source_name'])] = material
    REPORT['material_count'] = len(result)
    REPORT['texture_count'] = len(textures)
    return result


def main():
    # Source integrity and engine version are checked before importing.
    version = unreal.SystemLibrary.get_engine_version()
    REPORT['engine_version'] = version
    require(version.startswith('5.6.'), 'Usar Unreal Engine 5.6.x, version encontrada: ' + version)
    for relative, expected in MANIFEST['source_sha256'].items():
        source = ROOT / relative
        require(source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == expected,
                'Archivo incompleto o cambiado: ' + relative)
    options = unreal.FbxImportUI()
    for key, value in {
        'automated_import_should_detect_type': False,
        'mesh_type_to_import': unreal.FBXImportType.FBXIT_SKELETAL_MESH,
        'original_import_type': unreal.FBXImportType.FBXIT_SKELETAL_MESH,
        'import_as_skeletal': True, 'import_mesh': True,
        'import_animations': False, 'import_materials': False, 'import_textures': False,
        'create_physics_asset': True, 'skeleton': None,
    }.items():
        options.set_editor_property(key, value)
    data = options.get_editor_property('skeletal_mesh_import_data')
    for key, value in {
        'convert_scene': True, 'convert_scene_unit': True, 'force_front_x_axis': False,
        'import_uniform_scale': 1.0, 'import_meshes_in_bone_hierarchy': True,
        'import_morph_targets': False, 'import_mesh_lods': False,
        'update_skeleton_reference_pose': False, 'use_t0_as_ref_pose': False,
        'reorder_material_to_fbx_order': True,
        'normal_import_method': unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS,
    }.items():
        data.set_editor_property(key, value)
    mesh_path = MANIFEST['mesh_path']
    folder, name = mesh_path.rsplit('/', 1)
    assets = asset_import(ROOT / MANIFEST['fbx'], folder, name, options, unreal.FbxFactory())
    meshes = [a for a in assets if isinstance(a, unreal.SkeletalMesh)]
    # FBX parts must be combined into one asset, with the expected package name.
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    require(len(meshes) == 1 and isinstance(mesh, unreal.SkeletalMesh),
            'El FBX no se combino en una unica malla: ' + repr([a.get_path_name() for a in meshes]))
    REPORT['mesh_path'] = mesh.get_path_name()
    verify_bones(mesh)
    skeleton = relocate(mesh.get_editor_property('skeleton'), MANIFEST['skeleton_path'])
    physics = mesh.get_editor_property('physics_asset')
    require(physics is not None, 'No se genero el recurso de fisica de referencia.')
    existing_physics = unreal.EditorAssetLibrary.load_asset(MANIFEST['physics_path'])
    if existing_physics is not None and str(physics.get_path_name()).split('.')[0] != MANIFEST['physics_path']:
        require(isinstance(existing_physics, unreal.PhysicsAsset), 'La ruta de fisica tiene otro tipo de recurso.')
        physics = existing_physics
        mesh.set_editor_property('physics_asset', physics)
    else:
        physics = relocate(physics, MANIFEST['physics_path'])
    REPORT['skeleton_reference'] = skeleton.get_path_name()
    REPORT['physics_reference'] = physics.get_path_name()
    REPORT['exclude_from_mod'] = [MANIFEST['skeleton_path'], MANIFEST['physics_path']]
    materials = make_materials()
    slots = list(mesh.get_editor_property('materials'))
    assigned = []
    for slot in slots:
        names = [slot.get_editor_property('imported_material_slot_name'),
                 slot.get_editor_property('material_slot_name')]
        material = next((materials.get(canonical(n)) for n in names
                         if materials.get(canonical(n)) is not None), None)
        require(material is not None, 'No se reconocio el material FBX: ' + repr([str(n) for n in names]))
        slot.set_editor_property('material_interface', material)
        assigned.append(material.get_path_name())
    require(bool(slots), 'La malla no tiene materiales.')
    mesh.set_editor_property('materials', slots)
    # Bind to these placeholder paths; their cooked packages will be excluded,
    # so the installed mod resolves the game's original skeleton and physics.
    for asset in (skeleton, physics, mesh):
        require(unreal.EditorAssetLibrary.save_loaded_asset(asset), 'No se guardo: ' + asset.get_path_name())
    require(unreal.EditorAssetLibrary.save_directory('/Game/Mods/Jinx', only_if_is_dirty=False, recursive=True),
            'No se guardaron todos los materiales y texturas.')
    REPORT['assigned_materials'] = assigned
    # The runtime controller uses actual imported slot order, not manifest order.
    runtime_file = ROOT / 'Prototipo_UE4SS/Mods/Jinx_Adaptada_RV/Scripts/JinxRuntimeAssets.lua'
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    package_path = str(mesh.get_path_name()).split('.')[0]
    runtime_file.write_text(
        '-- Generated after Unreal import and verification.\nreturn {\n'
        '    imported_and_verified = true,\n'
        '    mesh_package = ' + json.dumps(package_path) + ',\n'
        '    mesh_object = ' + json.dumps(str(mesh.get_path_name())) + ',\n'
        '    materials = {\n' + ''.join('        ' + json.dumps(path) + ',\n' for path in assigned)
        + '    },\n}\n', encoding='utf-8')
    REPORT['runtime_material_slots'] = assigned
    REPORT['status'] = 'imported_and_verified'
    unreal.log('JINX: importacion y validacion terminadas. Falta cocinar y probar en el juego.')


try:
    main()
except Exception as error:
    REPORT['status'] = 'failed'
    REPORT['error'] = str(error)
    REPORT['traceback'] = traceback.format_exc()
    unreal.log_error(REPORT['traceback'])
    raise
finally:
    REPORT_FILE.write_text(json.dumps(REPORT, indent=2, ensure_ascii=False), encoding='utf-8')
