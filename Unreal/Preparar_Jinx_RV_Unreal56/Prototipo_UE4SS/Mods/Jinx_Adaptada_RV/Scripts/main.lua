-- Jinx visual prototype for RV There Yet?, build CL-20702.
-- Requires cooked, mounted assets and a compatible UE4SS installation.
local Spec = require("JinxRuntimeAssets")
local reported, lastCharacter, assets, snapshot = {}, nil, nil, nil
local pending, ticks = false, 0
local GARMENTS = {"LowerBodyClothes", "UpperBodyClothes", "SM_Glasses", "SM_Hat01"}

local function logOnce(key, message)
    if reported[key] then return end
    reported[key] = true
    print("[Jinx_Adaptada_RV] " .. message .. "\n")
end

local function read(object, key)
    local okay, result = pcall(function() return object[key] end)
    if okay then return result end
end

local function valid(object)
    if object == nil then return false end
    local okay, result = pcall(function() return object:IsValid() end)
    return okay and result == true
end

local function same(left, right)
    return valid(left) and valid(right) and left:GetAddress() == right:GetAddress()
end

local function isA(object, name)
    return valid(object) and object:IsA(name)
end

local function loadObject(packagePath, objectPath)
    local object = StaticFindObject(objectPath)
    if not valid(object) then
        LoadAsset(packagePath) -- All callers run in the game thread.
        object = StaticFindObject(objectPath)
    end
    return object
end

local function loadAssets()
    if not Spec.imported_and_verified or #Spec.materials == 0 then
        logOnce("unbuilt", "Falta importar y cocinar Jinx con el proyecto incluido.")
        return nil
    end
    if assets and valid(assets.mesh) then
        local complete = true
        for _, material in ipairs(assets.materials) do complete = complete and valid(material) end
        if complete then return assets end
    end
    -- Retry missing mounted packages every ten seconds.
    if ticks ~= 1 and ticks % 20 ~= 0 then return nil end
    local mesh = loadObject(Spec.mesh_package, Spec.mesh_object)
    if not isA(mesh, "/Script/Engine.SkeletalMesh") then
        logOnce("unmounted", "No se encontro la malla cocinada y montada de Jinx.")
        return nil
    end
    local materials = {}
    for index, objectPath in ipairs(Spec.materials) do
        local packagePath = objectPath:match("^(.-)%.[^%.]+$")
        local material = loadObject(packagePath, objectPath)
        if not isA(material, "/Script/Engine.MaterialInterface") then
            logOnce("material_missing", "Falta un material de Jinx; no se aplica la sustitucion.")
            return nil
        end
        materials[index] = material
    end
    assets = {mesh = mesh, materials = materials}
    return assets
end

local function localCharacter()
    for _, character in ipairs(FindAllOf("RGFirstPersonCharacter") or {}) do
        if isA(character, "/Script/Ride.RGFirstPersonCharacter") then
            local okay, controlled = pcall(function() return character:IsLocallyControlled() end)
            if okay and controlled then
                lastCharacter = character
                return character
            end
        end
    end
    -- While driving, possession can move to the vehicle. Keep the last pawn.
    if isA(lastCharacter, "/Script/Ride.RGFirstPersonCharacter") then return lastCharacter end
end

local function hideGarments(character)
    for _, field in ipairs(GARMENTS) do
        local component = read(character, field)
        if not valid(component) then component = read(character, field .. "_GEN_VARIABLE") end
        if isA(component, "/Script/Engine.MeshComponent")
                and same(component:GetOwner(), character)
                and read(component, "bOnlyOwnerSee") ~= true then
            -- Never propagate visibility to children, such as held items.
            if component:IsVisible() then component:SetVisibility(false, false) end
        end
    end
    -- FirstPersonMesh, FPP arms, UpperBodyClothesFPP and held items stay independent.
end

local function update()
    ticks = ticks + 1
    local character = localCharacter()
    if not character then return end
    local desired = loadAssets()
    if not desired then return end
    local body = read(character, "Mesh")
    if not isA(body, "/Script/Engine.SkeletalMeshComponent")
            or not same(body:GetOwner(), character)
            or read(body, "bOnlyOwnerSee") == true then return end
    local current = body:GetSkinnedAsset()
    if not valid(current) then return end
    local actorIdentity = character:GetFullName() .. ":" .. tostring(character:GetAddress())
    if not snapshot or snapshot.identity ~= actorIdentity or not same(snapshot.body, body) then
        snapshot = {identity = actorIdentity, body = body}
    end
    if not same(current, desired.mesh) then
        local okay, ragdolling = pcall(function() return character:IsRagdolling() end)
        if not okay or ragdolling then return end
        local skeleton = read(current, "Skeleton")
        if not same(skeleton, read(desired.mesh, "Skeleton")) then
            logOnce("skeleton_mismatch", "El esqueleto cargado difiere; no se cambia el cuerpo.")
            return
        end
        local physics = read(body, "PhysicsAssetOverride")
        if not valid(physics) then physics = read(current, "PhysicsAsset") end
        if not valid(physics) then
            logOnce("physics_missing", "No se encontro la fisica original del cuerpo.")
            return
        end
        local animation = body:GetAnimInstance()
        if not valid(animation) then return end
        snapshot.originalMesh, snapshot.physics = current, physics
        body:SetSkinnedAssetAndUpdate(desired.mesh, false)
        if not same(body:GetSkinnedAsset(), desired.mesh) then
            logOnce("mesh_failed", "El juego no acepto la malla de Jinx.")
            return
        end
        body:SetPhysicsAsset(physics, false)
        if not same(animation, body:GetAnimInstance()) then
            logOnce("animation_changed", "La instancia de animacion cambio; revisar movimientos dentro del juego.")
        end
        logOnce("applied:" .. actorIdentity, "Cuerpo de Jinx aplicado al personaje local; prototipo sin validacion en el juego.")
    end
    -- Use the imported slot order. Repair component overrides only when changed.
    for index, material in ipairs(desired.materials) do
        if not same(body:GetMaterial(index - 1), material) then body:SetMaterial(index - 1, material) end
    end
    hideGarments(character)
end

logOnce("started", "Controlador de prueba cargado. Necesita los recursos cocinados de Jinx.")
LoopAsync(500, function()
    if pending then return false end
    pending = true
    local scheduled, reason = pcall(function()
        ExecuteInGameThread(function()
            local okay, message = pcall(update)
            pending = false
            if not okay then logOnce("error:" .. tostring(message), "Error del prototipo: " .. tostring(message)) end
        end)
    end)
    if not scheduled then
        pending = false
        logOnce("scheduler_error", "No se pudo programar la actualizacion: " .. tostring(reason))
    end
    return false
end)
