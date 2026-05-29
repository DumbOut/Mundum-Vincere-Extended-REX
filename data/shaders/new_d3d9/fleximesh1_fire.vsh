
vs_1_1
dcl_position0 v0
dcl_blendweight v1
dcl_blendindices v2
dcl_normal0 v3
dcl_texcoord0 v4
#line 4 "fleximesh1_fire.vsh"
; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
; v0 = position
; v1 = blend weights
; v2 = blend indices
; v3 = normal
; v4 = texture coordinates
; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --

; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
; r0.w = Last blend weight
; r1 = Blend indices
; r2 = Temp position
; r3 = Temp normal
; r4 = Blended position in camera space
; r5 = Blended normal in camera space
; r6 = view space vertex position
; r8.x = fog exponent
; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --

; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
; oPos = Output position
; oD0 = Diffuse
; oD1 = Specular
; oT0 = texture coordinates
; -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
#line 31 "fleximesh1_fire.vsh"
mul r1, v2.zyxw, c[0].wwww
#line 35 "fleximesh1_fire.vsh"
dp3 r0.w, v1.xyz, c[0].xzz; 
add r0.w, -r0.w, c[0].x
#line 39 "fleximesh1_fire.vsh"
mov a0.x, r1.x
m3x3 r4, v0, c[a0.x + 15]
m3x3 r5, v3, c[a0.x + 15]
#line 44 "fleximesh1_fire.vsh"
mul r4, r4, v1.xxxx
mul r5, r5, v1.xxxx
#line 49 "fleximesh1_fire.vsh"
mov r11.x, c[a0.x + 15 + 0].w
mov r11.y, c[a0.x + 15 + 1].w
mov r11.z, c[a0.x + 15 + 2].w
mov r11.w, c0.x
#line 55 "fleximesh1_fire.vsh"
mov a0.x, r1.y
m3x3 r2, v0, c[a0.x + 15]
m3x3 r3, v3, c[a0.x + 15]
#line 60 "fleximesh1_fire.vsh"
mad r4, r2, r0.wwww, r4
mad r5, r3, r0.wwww, r5
#line 64 "fleximesh1_fire.vsh"
add r4, r4, r11
#line 67 "fleximesh1_fire.vsh"
mad r4 , r5, c[0].z, r4
#line 70 "fleximesh1_fire.vsh"
mov r4.w, c[0].x
m4x4 r6, r4, c[1]
mov oPos, r6
#line 75 "fleximesh1_fire.vsh"
mov oD0, c[0].x 
mov oD1, c[0].yyyy 

;mov oD0.y, c0.z
; Copy texture coordinate
mov oT0, v4
#line 83 "fleximesh1_fire.vsh"
; Calculate the fog using D3DFOG_EXP
;mul r8.x, -c[0].w, r6.z ; - (fog_exp_density * z_dist)
;exp oFog, r8.x ; evaluate exponential function (2^ ( -fog_exp_density * z_dist))

mov oFog, c[0].y
