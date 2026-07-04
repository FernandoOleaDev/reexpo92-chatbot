---
title: Cómo funciona la reconstrucción 3D
url: /como-funciona
---

# La reconstrucción 3D de la Expo 92

La reconstrucción usa **un solo motor: Unity 6.3 WebGL**, compartido entre escritorio y móvil (en móvil, con ajustes de calidad más agresivos). Funcionará en el navegador, sin instalar nada.

## Dos niveles de trabajo

1. **Modeladores**: investigan la ficha, modelan el pabellón en **GLB** (validación automática en el navegador con gltf-transform), lo suben y pasa por revisión. Al aprobarse, se publica en el **banco de modelos** para descargar y mejorar (con crédito en cadena).
2. **Desarrolladores de Unity**: cogen un GLB aprobado, montan el prefab (URP, LODs, materiales), lo empaquetan como **Addressable** y lo suben; también pasa por revisión.

## Dos capas

- Una **capa canónica** con los datos neutrales (geometría, medidas).
- Una **capa de realce Unity** (iluminación, shaders, efectos). Gran parte se comparte entre plataformas.

## Estado

El pipeline de modelos ya está en marcha; los Addressables, en desarrollo; el recinto WebGL caminable, en el futuro. Hay un roadmap por fases.
