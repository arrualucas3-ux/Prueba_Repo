-- Contract tests with fake Unreal objects; these do not run UE4SS or the game.
local nextAddress=0
local function object(className)
    nextAddress=nextAddress+1
    local o={address=nextAddress, alive=true, className=className, owner=nil}
    function o:IsValid() return self.alive end
    function o:GetAddress() return self.address end
    function o:IsA(name)
        return self.className==name or (self.className=="/Script/Engine.SkeletalMeshComponent" and name=="/Script/Engine.MeshComponent")
    end
    function o:GetFullName() return self.className..":"..self.address end
    function o:GetOwner() return self.owner end
    return o
end
local skeleton=object("/Script/Engine.Skeleton")
local physics=object("/Script/Engine.PhysicsAsset")
local original=object("/Script/Engine.SkeletalMesh");original.Skeleton=skeleton;original.PhysicsAsset=physics
local jinx=object("/Script/Engine.SkeletalMesh");jinx.Skeleton=skeleton
local material=object("/Script/Engine.MaterialInterface")
local animation=object("/Script/Engine.AnimInstance")
local char=object("/Script/Ride.RGFirstPersonCharacter");char.controlled=true;char.ragdoll=true
function char:IsLocallyControlled() return self.controlled end
function char:IsRagdolling() return self.ragdoll end
local body=object("/Script/Engine.SkeletalMeshComponent");body.owner=char;body.current=original
body.mat={};body.meshChanges=0;body.materialChanges=0;body.physicsChanges=0
function body:GetSkinnedAsset() return self.current end
function body:SetSkinnedAssetAndUpdate(mesh,reinit) assert(reinit==false);self.current=mesh;self.meshChanges=self.meshChanges+1 end
function body:GetAnimInstance() return animation end
function body:SetPhysicsAsset(asset,reinit) assert(asset==physics and reinit==false);self.physicsChanges=self.physicsChanges+1 end
function body:GetMaterial(index) return self.mat[index] end
function body:SetMaterial(index,value) self.mat[index]=value;self.materialChanges=self.materialChanges+1 end
char.Mesh=body
local garment=object("/Script/Engine.MeshComponent");garment.owner=char;garment.visible=true
function garment:IsVisible() return self.visible end
function garment:SetVisibility(visible,propagate) assert(propagate==false);self.visible=visible end
char.LowerBodyClothes=garment
local fpp=object("/Script/Engine.MeshComponent");fpp.owner=char;fpp.visible=true
char.UpperBodyClothesFPP=fpp
local remote=object("/Script/Ride.RGFirstPersonCharacter")
function remote:IsLocallyControlled() return false end
local spec={imported_and_verified=true,mesh_package="/Game/Mods/Jinx/SK_Jinx_RV",mesh_object="/Game/Mods/Jinx/SK_Jinx_RV.SK_Jinx_RV",materials={"/Game/Mods/Jinx/Materials/M.M"}}
package.preload.JinxRuntimeAssets=function() return spec end
local queue, loads, calls={},0,0
local mounted=false
function LoadAsset(path) loads=loads+1 end
function StaticFindObject(path)
    if not mounted then return nil end
    return path==spec.mesh_object and jinx or material
end
function FindAllOf(name) assert(name=="RGFirstPersonCharacter");return {remote,char} end
function LoopAsync(delay,fn) assert(delay==500);loopCallback=fn end
function ExecuteInGameThread(fn) queue[#queue+1]=fn end
local function tick()
    loopCallback();assert(#queue==1)
    local fn=table.remove(queue,1);fn();calls=calls+1
end
dofile(arg[1])
loopCallback();loopCallback();loopCallback();assert(#queue==1,"Callbacks must not accumulate")
table.remove(queue,1)();calls=calls+1
assert(body.meshChanges==0 and loads==1,"Missing assets must not change pawn")
mounted=true
for i=1,19 do tick() end
assert(body.meshChanges==0,"Ragdoll must defer substitution")
char.ragdoll=false;tick()
assert(body.meshChanges==1 and body.physicsChanges==1 and body.materialChanges==1)
assert(body:GetMaterial(0)==material and garment.visible==false and fpp.visible==true)
tick();assert(body.meshChanges==1 and body.materialChanges==1,"Stable assets must not reset mesh or materials")
body.mat[0]=original;tick();assert(body.materialChanges==2 and body.meshChanges==1,"Repair material only")
char.controlled=false;tick();assert(body.meshChanges==1,"Driving retains pawn without resetting mesh")
body.current=original;tick();assert(body.meshChanges==2,"An overwritten mesh can be reapplied")
char.controlled=true;body.current=original;jinx.Skeleton=object("/Script/Engine.Skeleton");tick()
assert(body.meshChanges==2,"Incompatible skeleton must not be applied")
jinx.Skeleton=skeleton;char.alive=false;tick();assert(body.meshChanges==2,"Destroyed pawn must not be used")
print("JINX_CONTRACT_TESTS_PASSED: queue, missing assets, ragdoll, local selection, physics, FPP visibility, stable mesh, material repair, driving, overwritten mesh, incompatible skeleton, destroyed pawn")
