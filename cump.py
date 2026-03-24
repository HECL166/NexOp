import pandas as pd
import os
import re

def limpiar_cruce(valor):
    if pd.isna(valor): 
        return ""
    texto = str(valor).replace('\xa0', ' ').replace('\n', '').replace('\r', '').replace('_x000D_', '').strip().upper()
    if texto in ['NAN', 'NONE', '', '-']: 
        return ""
        
    if texto.endswith('.0'): 
        texto = texto[:-2]
        
    texto = texto.lstrip('0')
    if texto == "": 
        texto = "0"
        
    return texto


# !!!!!!!!!!!!!!!!!!!Esto hay que revisarlo por que LH Si que cuenta para que sea la misma descripción
'''
def flexibilizar_descripcion_local(desc):
    desc_flex = re.sub(r'\d+', '#', str(desc))
    desc_flex = re.sub(r'\b(LH|RH|FWD|AFT|L|R)\b', '*', desc_flex)
    return re.sub(r'\s+', ' ', desc_flex).strip().upper()
'''

def fase_carga_filtrado():
    print("="*60)
    print("INICIO IDENTIFICADOR (MODO DIAGNÓSTICO EXTREMO)")
    print("="*60)

    if not os.path.exists('outputs'):
        os.makedirs('outputs')

    jerarquia_input = input("Introduce la jerarquía PEPs: ")
    jerarquia_pep = [pep.strip() for pep in jerarquia_input.split('>')]

    archivo_AC_mini = 'A_C_MINI.xlsx'
    archivo_tasar = 'TASAR.xlsx'
    archivo_indust = 'indust.xlsx'
    archivo_catalogo = 'catalogo.xlsx'

    try:
        # =====================================================================
        # 1. CARGA DE TASAR
        # =====================================================================
        print(f"\n[Paso 1] Cargando '{archivo_tasar}'...")
        df_tasar_raw = pd.read_excel(archivo_tasar, sheet_name='PD-SUMMARY', dtype=str)
        df_tasar_ok = df_tasar_raw[df_tasar_raw['02.00'].astype(str).str.upper() == 'Y'].copy()
        task_refs_validas = set(df_tasar_ok['TASK REFERENCE'].unique())
        
        print(f"Task Refs válidas extraídas: {len(task_refs_validas)}")
        if len(task_refs_validas) > 0:
            print(f"Ejemplos Task Ref: {list(task_refs_validas)[:3]}")

        # =====================================================================
        # 2. CARGA DE A/C MINI (FILTRO: RUTA + REV)
        # =====================================================================
        print(f"\n[Paso 2] Cargando '{archivo_AC_mini}'...")
        df_ac_mini_raw = pd.read_excel(archivo_AC_mini, sheet_name='Cruce Lanzado MSN136', header=1, dtype=str)
        df_ac_mini_filtrado = df_ac_mini_raw[df_ac_mini_raw['Reference'].isin(task_refs_validas)].copy()

        df_ac_mini_filtrado['LLAVE_RutaRev'] = df_ac_mini_filtrado['RUTA SAN PABLO'].apply(limpiar_cruce) + "-" + df_ac_mini_filtrado['REV SN PABLO COPIADA'].apply(limpiar_cruce)
        claves_ac_mini = set(df_ac_mini_filtrado['LLAVE_RutaRev'].unique())
        
        print(f" Llaves (Ruta-Rev) generadas en A/C Mini: {len(claves_ac_mini)}")
        if len(claves_ac_mini) > 0:
            print(f"Ejemplos llaves A/C Mini: {list(claves_ac_mini)[:5]}")

        # =====================================================================
        # 3. FILTRADO DE OPERACIONES
        # =====================================================================
        print(f"\n[Paso 3] Cargando Operaciones de '{archivo_indust}'...")
        df_operaciones_raw = pd.read_excel(archivo_indust, sheet_name='Operaciones', dtype=str)
        
        df_operaciones_raw['LLAVE_RutaRev'] = df_operaciones_raw['Ruta Local'].apply(limpiar_cruce) + "-" + df_operaciones_raw['Rev.'].apply(limpiar_cruce)
        
        print(f"Total operaciones en crudo: {len(df_operaciones_raw)}")
        if len(df_operaciones_raw) > 0:
            print(f"Ejemplos de llaves fabricadas por Operaciones: {df_operaciones_raw['LLAVE_RutaRev'].head(5).tolist()}")

        # Aplicamos cruce con AC Mini
        df_operaciones = df_operaciones_raw[df_operaciones_raw['LLAVE_RutaRev'].isin(claves_ac_mini)].copy()
        print(f"   -> Sobreviven al cruce con A/C Mini: {len(df_operaciones)}")

        # Filtrado de patrones
        patrones_validos = ['OT', 'BT', 'RMV', 'INS', 'ACC', 'ITL', 'SVC', 'RPL', 'APURUN', 'EGR', 'HPGC', 'LPGC']
        patrones_ejecutables = ['ITL ALU', 'ADM', 'LKC VCS', 'LKC PP VCS', 'LKC TCS', 'LKC TCS HPGC/APU',  'REPORT', 'LKC AGS', 'LKC ALU APU', 'LKC ALU EGR', 'LKC ALU HPGC']
        
        operaciones_validas = []
        for idx, row in df_operaciones.iterrows():
            nombre_op = str(row['Nombre Operación']).strip().upper()
            if any(patron_ex in nombre_op for patron_ex in patrones_ejecutables): continue
                
            patron_encontrado = None
            for patron in patrones_validos:
                if re.search(r'\b' + re.escape(patron), nombre_op):
                    patron_encontrado = patron
                    break 
            
            if patron_encontrado:
                row_dict = row.to_dict()
                row_dict['PATRON_DETECTADO'] = patron_encontrado 
                operaciones_validas.append(row_dict)
                
        df_operaciones_validas = pd.DataFrame(operaciones_validas)
        print(f"   -> Sobreviven al filtro de Patrones: {len(df_operaciones_validas)}")

        # Agrupación y Parejas (Sinergias)
        if not df_operaciones_validas.empty:
            df_operaciones_validas['DESC_LIMPIA'] = df_operaciones_validas['Descripción Operación'].astype(str).str.strip().str.upper()
            df_operaciones_validas['ESTACION_LIMPIA'] = df_operaciones_validas['Estación Oper.'].astype(str).str.strip().str.upper()
            df_operaciones_validas['DESC_FLEXIBLE'] = df_operaciones_validas['DESC_LIMPIA'].apply(flexibilizar_descripcion_local)
            
            df_operaciones_final = df_operaciones_validas.groupby(['PATRON_DETECTADO', 'DESC_FLEXIBLE', 'ESTACION_LIMPIA']).filter(lambda x: len(x) >= 2).copy()
            df_operaciones_final = df_operaciones_final.drop(columns=['PATRON_DETECTADO', 'DESC_LIMPIA', 'ESTACION_LIMPIA', 'DESC_FLEXIBLE'])
        else:
            df_operaciones_final = pd.DataFrame() 

        print(f"   -> Operaciones Finales Válidas (con pareja): {len(df_operaciones_final)}")

        # =====================================================================
        # 3.2 DOCUMENTOS Y MATERIALES (VINCULACIÓN: RUTA + REV + OP)
        # =====================================================================
        print(f"\n[Paso 3.2] Cargando Documentos...")
        df_documentos_raw = pd.read_excel(archivo_indust, sheet_name='Documentos', dtype=str)
        df_materiales_raw = pd.read_excel(archivo_indust, sheet_name='Materiales', dtype=str)

        if not df_operaciones_final.empty:
            df_operaciones_final['LLAVE_RutaRevOp'] = (
                df_operaciones_final['Ruta Local'].apply(limpiar_cruce) + "-" + 
                df_operaciones_final['Rev.'].apply(limpiar_cruce) + "-" + 
                df_operaciones_final['Operación'].apply(limpiar_cruce)
            )
            claves_operaciones_finales = set(df_operaciones_final['LLAVE_RutaRevOp'].unique())
        else:
            claves_operaciones_finales = set()

        print(f"Documentos en Excel original: {len(df_documentos_raw)}")
        print(f"Llaves de 3 pines (Ruta-Rev-Op) que pediremos a Documentos: {len(claves_operaciones_finales)}")
        if len(claves_operaciones_finales) > 0:
            print(f"Ejemplos de lo que pedimos: {list(claves_operaciones_finales)[:5]}")

        # Fabricar llaves en Documentos
        df_documentos_raw['LLAVE_RutaRevOp'] = (
            df_documentos_raw['Ruta'].apply(limpiar_cruce) + "-" + 
            df_documentos_raw['Rev.'].apply(limpiar_cruce) + "-" + 
            df_documentos_raw['Operación'].apply(limpiar_cruce)
        )
        
        if len(df_documentos_raw) > 0:
            print(f"Ejemplos de llaves que Documentos ha logrado fabricar: {df_documentos_raw['LLAVE_RutaRevOp'].dropna().head(5).tolist()}")

        df_documentos = df_documentos_raw[df_documentos_raw['LLAVE_RutaRevOp'].isin(claves_operaciones_finales)].copy()
        
        # Fabricar llaves en Materiales
        df_materiales_raw['LLAVE_RutaRevOp'] = (
            df_materiales_raw['Ruta'].apply(limpiar_cruce) + "-" + 
            df_materiales_raw['Rev.'].apply(limpiar_cruce) + "-" + 
            df_materiales_raw['Operación'].apply(limpiar_cruce)
        )
        df_materiales = df_materiales_raw[df_materiales_raw['LLAVE_RutaRevOp'].isin(claves_operaciones_finales)].copy()

        print(f"Documentos que cruzaron con éxito: {len(df_documentos)}")
        print(f"Materiales que cruzaron con éxito: {len(df_materiales)}")
        # =====================================================================

        # 4. CARGA DE CATÁLOGO
        print(f"\n[Paso 4] Cargando '{archivo_catalogo}'...")
        df_catalogo_raw = pd.read_excel(archivo_catalogo, dtype=str)       
        lista_catalogo = set(df_catalogo_raw['Nombre Operación'].dropna().str.upper().unique())

        tablas = {
            "Tasar_Filtrado_Y": df_tasar_ok,
            "AC_Mini_Filtrado": df_ac_mini_filtrado,
            "Operaciones_Finales": df_operaciones_final,
            "Documentos": df_documentos,
            "Materiales": df_materiales,
            "Catalogo_Nombres": pd.DataFrame(list(lista_catalogo), columns=["Nombre Operación"])
        }

        print("\n" + "="*50)
        print("RESUMEN DE EXPORTACION")
        print("="*50)

        for nombre, df_tabla in tablas.items():
            columnas_a_borrar = [col for col in ['LLAVE_RutaRev', 'LLAVE_RutaRevOp'] if col in df_tabla.columns]
            if columnas_a_borrar: df_tabla = df_tabla.drop(columns=columnas_a_borrar)
                
            ruta_completa = f"outputs/{nombre}_COMPLETO.xlsx"
            df_tabla.to_excel(ruta_completa, index=False)
            print(f"Guardado ({len(df_tabla)} registros) en: {ruta_completa}")

        print("\nFASE 1 Completa con Éxito")
        return tablas, jerarquia_pep

    except Exception as e:
        print(f"\n[ERROR] Problema inesperado: {e}")
        return None

if __name__ == '__main__':          
    resultado_fase_1 = fase_carga_filtrado()