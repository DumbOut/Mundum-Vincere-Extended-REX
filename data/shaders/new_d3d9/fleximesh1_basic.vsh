
vs_1_1
dcl_position0 v0
dcl_blendweight v1
dcl_blendindices v2
dcl_normal0 v3
dcl_texcoord0 v4
#line 5 "fleximesh1_basic.vsh"
mul r1, v2.zyxw, c[0].wwww
#line 9 "fleximesh1_basic.vsh"
dp3 r0.w, v1.xyz, c[0].xzz; 
add r0.w, -r0.w, c[0].x
#line 13 "fleximesh1_basic.vsh"
mov a0.x, r1.x
m3x3 r4, v0, c[a0.x + 24]
#line 17 "fleximesh1_basic.vsh"
mov r4, c[0].z
mul r4, r4, v1.xxxx
#line 22 "fleximesh1_basic.vsh"
mov r11.x, c[a0.x + 24 + 0].w
mov r11.y, c[a0.x + 24 + 1].w
mov r11.z, c[a0.x + 24 + 2].w
mov r11.w, c0.x
#line 28 "fleximesh1_basic.vsh"
mov a0.x, r1.y
mov r2.w, c[0].z
m3x3 r2, v0, c[a0.x + 24]
#line 33 "fleximesh1_basic.vsh"
mad r4, r2, r0.wwww, r4
#line 36 "fleximesh1_basic.vsh"
add r4, r4, r11
#line 39 "fleximesh1_basic.vsh"
mov r4.w, c[0].x
m4x4 r6, r4, c[2]
mov oPos, r6

mov oD0, c[0].y
mov oD1, c[0].zzzz
mov oFog, c[0].z
