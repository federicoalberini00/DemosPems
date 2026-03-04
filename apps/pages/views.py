import pandas as pd
import json
from django.shortcuts import render,redirect
import numpy as np
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
@login_required
def export_results_excel(request):
    tipo = request.GET.get('type', 'economica')
    data_ele = request.session.get('dati_elettrici', [])
    data_gas = request.session.get('dati_benzina', [])
    area = float(request.session.get('area_pannelli', 3000))
    
    # Parametri economici dalla sessione
    p_acquisto = float(request.session.get('prezzo_acquisto', 0.10))
    p_vendita = float(request.session.get('prezzo_vendita', 0.05))
    p_gasolio = float(request.session.get('prezzo_gasolio', 1.75))
    
    KG_CO2_KWH = 0.28   
    KG_CO2_LITRO = 2.68  
    EFF, PR = 0.18, 0.75
    hours = list(range(24))

    if not data_ele:
        return HttpResponse("Dati elettrici mancanti.", status=400)

    # 1. Calcolo Gasolio (Litri e Costo)
    litri_totali = 0
    if data_gas:
        df_gas = pd.DataFrame(data_gas)
        litri_totali = pd.to_numeric(df_gas['consumption_in_l'], errors='coerce').sum()
    
    spesa_gasolio_totale = litri_totali * p_gasolio
    co2_gasolio_totale = litri_totali * KG_CO2_LITRO

    # 2. Elaborazione Dati Elettrici (Profili Orari per precisione millesimale)
    df = pd.DataFrame(data_ele)
    df['Date'] = pd.to_datetime(df['Date'])
    daily_df = df.groupby(df['Date'].dt.date).agg({'Consumption (Wh)': 'sum'}).reset_index()
    daily_df['Date'] = pd.to_datetime(daily_df['Date'])
    
    def get_solar_h(daily_t):
        curve = [max(0, np.sin((h-6)*np.pi/14)) if 6 <= h <= 20 else 0 for h in hours]
        f = daily_t / sum(curve) if sum(curve) > 0 else 0
        return [c * f for c in curve]

    def get_cons_h(daily_t):
        b = (daily_t * 0.20) / 24
        w = (daily_t * 0.80) / 10
        return [w + b if 8 <= h <= 18 else b for h in hours]

    results = []
    for _, row in daily_df.iterrows():
        m = row['Date'].month
        irr = {12:789.7, 1:789.7, 2:789.7, 3:2756.6, 4:2756.6, 5:2756.6, 6:5676.7, 7:5676.7, 8:5676.7}.get(m, 2748.9)
        
        prod_gg = irr * area * EFF * PR
        cons_gg = row['Consumption (Wh)']
        
        s_prof = get_solar_h(prod_gg)
        c_prof = get_cons_h(cons_gg)
        
        costo_gg, guadagno_gg, co2_potenziale_gg, co2_rete_reale_gg, co2_risp_gg = 0, 0, 0, 0, 0
        
        for s, c in zip(s_prof, c_prof):
            co2_potenziale_gg += (c / 1000) * KG_CO2_KWH
            co2_risp_gg += (s / 1000) * KG_CO2_KWH
            
            if c > s:
                costo_gg += ((c - s) / 1000) * p_acquisto
                co2_rete_reale_gg += ((c - s) / 1000) * KG_CO2_KWH
            else:
                guadagno_gg += ((s - c) / 1000) * p_vendita

        if tipo == 'economica':
            results.append({
                'Data': row['Date'].strftime('%d/%m/%Y'),
                'Costo Prelievo Rete (€)': costo_gg,
                'Guadagno Vendita PV (€)': guadagno_gg,
            })
        else:
            results.append({
                'Data': row['Date'].strftime('%d/%m/%Y'),
                'CO2 Potenziale No PV (kg)': co2_potenziale_gg,
                'CO2 Rete Residua (kg)': co2_rete_reale_gg,
                'CO2 Abbattuta PV (kg)': co2_risp_gg
            })

    # 4. Creazione DataFrame Export dai risultati giornalieri
    df_export = pd.DataFrame(results)
    numeric_cols = df_export.select_dtypes(include=[np.number]).columns
    totals = df_export[numeric_cols].sum()

    # Inizializziamo la lista per le righe di riepilogo
    extra_rows = []

    if tipo == 'economica':
        # 1. Totale Parziale Rete (mostra tutti i totali di colonna)
        rete_row = {col: totals[col] for col in numeric_cols}
        rete_row['Data'] = 'TOTALE PARZIALE RETE'
        extra_rows.append(rete_row)
        
        # 2. Totale Spesa Gasolio (SOLO valore nella prima colonna numerica, le altre vuote)
        gas_row = {col: "" for col in numeric_cols} # Inizializza tutte le colonne come vuote
        gas_row['Data'] = 'TOTALE SPESA GASOLIO'
        gas_row['Costo Prelievo Rete (€)'] = spesa_gasolio_totale
        extra_rows.append(gas_row)
        
        # 3. Totale Generale (SOLO somma finale nella prima colonna, le altre vuote)
        summary_row = {col: "" for col in numeric_cols}
        summary_row['Data'] = 'TOTALE GENERALE (RETE + GASOLIO)'
        summary_row['Costo Prelievo Rete (€)'] = totals['Costo Prelievo Rete (€)'] + spesa_gasolio_totale
        extra_rows.append(summary_row)

    else:
        # Logica per Report CO2
        # 1. Totale Parziale Elettrico
        rete_co2_row = {col: totals[col] for col in numeric_cols}
        rete_co2_row['Data'] = 'TOTALE PARZIALE RETE'
        extra_rows.append(rete_co2_row)

        # 2. Emissioni Gasolio (Solo colonna Rete Residua)
        gas_co2_row = {col: "" for col in numeric_cols}
        gas_co2_row['Data'] = 'EMISSIONI GASOLIO'
        gas_co2_row['CO2 Rete Residua (kg)'] = co2_gasolio_totale
        extra_rows.append(gas_co2_row)
        
        # 3. Emissioni Totali Reali (Solo colonna Rete Residua)
        summary_co2_row = {col: "" for col in numeric_cols}
        summary_co2_row['Data'] = 'EMISSIONI TOTALI REALI'
        summary_co2_row['CO2 Rete Residua (kg)'] = totals['CO2 Rete Residua (kg)'] + co2_gasolio_totale
        extra_rows.append(summary_co2_row)

    # Aggiunta delle righe al DataFrame
    if extra_rows:
        df_export = pd.concat([df_export, pd.DataFrame(extra_rows)], ignore_index=True)

    # 5. Generazione File Excel
    filename = f"Analisi_{tipo}_PEMS.xlsx"
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    
    df_export.to_excel(response, index=False, engine='openpyxl')
    return response

@login_required
def economic_view(request):
    data_ele = request.session.get('dati_elettrici', [])
    data_gas = request.session.get('dati_benzina', [])
    
    # Recupero parametri (come nel tuo codice originale)
    area = float(request.session.get('area_pannelli', 3000))
    prezzo_acquisto = float(request.session.get('prezzo_acquisto', 0.10))
    prezzo_vendita = float(request.session.get('prezzo_vendita', 0.05))
    prezzo_gasolio = float(request.session.get('prezzo_gasolio', 1.75))

    request.session.modified = True

    # Calcolo Gasolio (rimane invariato perché è già in litri)
    total_gas_liters = 0
    total_gas_cost = 0
    if data_gas:
        df_gas = pd.DataFrame(data_gas)
        total_gas_liters = pd.to_numeric(df_gas['consumption_in_l'], errors='coerce').sum()
        total_gas_cost = total_gas_liters * prezzo_gasolio

    if not data_ele:
        return render(request, 'pages/economic.html', {
            'segment': 'economic', 
            'area_pannelli': area,
            'prezzo_acquisto': prezzo_acquisto, 
            'prezzo_vendita': prezzo_vendita,
            'prezzo_gasolio': prezzo_gasolio,
            'total_gas_cost': round(float(total_gas_cost), 2),
            'total_gas_liters': round(float(total_gas_liters), 2),
        })

    df = pd.DataFrame(data_ele)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # TRASFORMAZIONE: Raggruppiamo e convertiamo immediatamente in kWh (/1000)
    daily_df = df.groupby(df['Date'].dt.date).agg({'Consumption (Wh)': 'sum'}).reset_index()
    daily_df['Consumption (kWh)'] = daily_df['Consumption (Wh)'] / 1000
    daily_df['Date'] = pd.to_datetime(daily_df['Date'])
    
    hours = list(range(24))
    
    # Funzioni di profilo aggiornate per lavorare in kWh
    def get_solar_h(daily_total_kwh):
        curve = [max(0, np.sin((h-6)*np.pi/14)) if 6 <= h <= 20 else 0 for h in hours]
        factor = daily_total_kwh / sum(curve) if sum(curve) > 0 else 0
        return [float(c * factor) for c in curve]

    def get_cons_h(daily_total_kwh):
        base = (daily_total_kwh * 0.20) / 24
        work = (daily_total_kwh * 0.80) / 10
        return [float(work + base if 8 <= h <= 18 else base) for h in hours]

    def get_irr(m):
        if m in [12, 1, 2]: return 789.7
        if m in [3, 4, 5]: return 2756.6
        if m in [6, 7, 8]: return 5676.7
        return 2748.9

    total_cost_period = 0
    total_gain_period = 0
    EFF, PR = 0.18, 0.75

    for _, row in daily_df.iterrows():
        # Calcolo produzione giornaliera direttamente in kWh
        d_solar_kwh = (get_irr(row['Date'].month) * area * EFF * PR) / 1000
        d_cons_kwh = row['Consumption (kWh)']
        
        s_profile = get_solar_h(d_solar_kwh)
        c_profile = get_cons_h(d_cons_kwh)
        
        for s, c in zip(s_profile, c_profile):
            # Calcolo costi (s e c sono già in kWh, quindi non dividiamo più per 1000 qui)
            if s > c: 
                total_gain_period += (s - c) * prezzo_vendita
            else: 
                total_cost_period += (c - s) * prezzo_acquisto

    # Statistiche stagionali in kWh
    daily_df['Stagione'] = daily_df['Date'].dt.month.map(lambda m: 
        'Inverno' if m in [12,1,2] else 'Primavera' if m in [3,4,5] else 'Estate' if m in [6,7,8] else 'Autunno')
    
    seasonal_stats = daily_df.groupby('Stagione')['Consumption (kWh)'].mean()
    stagioni_list = ['Inverno', 'Primavera', 'Estate', 'Autunno']
    typical_days = {}

    for stag in stagioni_list:
        media_c_kwh = seasonal_stats.get(stag, 0)
        m_ref = {'Inverno': 1, 'Primavera': 4, 'Estate': 7, 'Autunno': 10}[stag]
        teorico_s_kwh = (get_irr(m_ref) * area * EFF * PR) / 1000
        
        typical_days[stag] = {
            'solar': get_solar_h(teorico_s_kwh),
            'cons': get_cons_h(media_c_kwh)
        }

    context = {
        'segment': 'economic',
        'stagioni_list': stagioni_list,
        'seasonal_labels': json.dumps(stagioni_list),
        # Dati passati ai grafici ora in kWh
        'seasonal_cons': json.dumps([float(seasonal_stats.get(s, 0)) for s in stagioni_list]),
        'seasonal_prod': json.dumps([float((get_irr({'Inverno': 1, 'Primavera': 4, 'Estate': 7, 'Autunno': 10}[s]) * area * EFF * PR) / 1000) for s in stagioni_list]),
        'total_cost': round(float(total_cost_period), 2),
        'total_gain': round(float(total_gain_period), 2),
        'total_gas_cost': round(float(total_gas_cost), 2),
        'total_gas_liters': round(float(total_gas_liters), 2),
        'typical_days': json.dumps(typical_days),
        'hours': json.dumps(hours),
        'area_pannelli': area,
        'prezzo_acquisto': prezzo_acquisto,
        'prezzo_vendita': prezzo_vendita,
        'prezzo_gasolio': prezzo_gasolio,
    }
    return render(request, 'pages/economic.html', context)


@login_required
def co2_view(request):
    data_ele = request.session.get('dati_elettrici', [])
    data_gas = request.session.get('dati_benzina', [])
    area = float(request.session.get('area_pannelli', 3000))
    
    KG_CO2_KWH = 0.28   
    KG_CO2_LITRO = 2.68  
    KG_CO2_ALBERO = 20.0 

    if not data_ele and not data_gas:
        return render(request, 'pages/co2.html', {'segment': 'co2'})

    litri_totali = 0
    if data_gas:
        df_gas = pd.DataFrame(data_gas)
        litri_totali = pd.to_numeric(df_gas['consumption_in_l'], errors='coerce').sum()
    co2_gasolio = litri_totali * KG_CO2_LITRO

    co2_rete_reale = 0
    co2_potenziale_senza_pv = 0
    co2_risparmiata_solare = 0
    kwh_consumati_totali = 0

    if data_ele:
        df = pd.DataFrame(data_ele)
        df['Date'] = pd.to_datetime(df['Date'])
        daily_df = df.groupby(df['Date'].dt.date).agg({'Consumption (Wh)': 'sum'}).reset_index()
        daily_df['Date'] = pd.to_datetime(daily_df['Date'])
        
        EFF, PR = 0.18, 0.75
        hours = list(range(24))

        def get_solar_h(daily_t):
            curve = [max(0, np.sin((h-6)*np.pi/14)) if 6 <= h <= 20 else 0 for h in hours]
            f = daily_t / sum(curve) if sum(curve) > 0 else 0
            return [c * f for c in curve]

        def get_cons_h(daily_t):
            b = (daily_t * 0.20) / 24
            w = (daily_t * 0.80) / 10
            return [w + b if 8 <= h <= 18 else b for h in hours]

        for _, row in daily_df.iterrows():
            m = row['Date'].month
            irr = {12:789.7, 1:789.7, 2:789.7, 3:2756.6, 4:2756.6, 5:2756.6, 6:5676.7, 7:5676.7, 8:5676.7}.get(m, 2748.9)
            
            prod_gg = irr * area * EFF * PR
            cons_gg = row['Consumption (Wh)']
            kwh_consumati_totali += cons_gg / 1000
            
            s_prof = get_solar_h(prod_gg)
            c_prof = get_cons_h(cons_gg)
            
            for s, c in zip(s_prof, c_prof):
                # 1. Base di confronto: CO2 che emetteresti con il profilo ricostruito
                co2_potenziale_senza_pv += (c / 1000) * KG_CO2_KWH 
                
                # 2. Emissione reale: Solo quello che prelevi dalla rete (dove C > S)
                if c > s:
                    co2_rete_reale += ((c - s) / 1000) * KG_CO2_KWH
                
                # 3. CO2 Risparmiata: Tutta la produzione solare del profilo (S)
                co2_risparmiata_solare += (s / 1000) * KG_CO2_KWH

    # Calcolo totali includendo il gasolio
    emissioni_totali_senza_pv = co2_gasolio + co2_potenziale_senza_pv
    emissioni_totali_reali = co2_gasolio + co2_rete_reale

    context = {
        'segment': 'co2',
        'co2_gas': round(co2_gasolio, 1),
        'co2_ele_reale': round(co2_rete_reale, 1),
        'co2_ele_potenziale': round(co2_potenziale_senza_pv, 1),
        'co2_risparmiata': round(co2_risparmiata_solare, 1),
        'co2_totale_reale': round(emissioni_totali_reali, 1),
        'co2_totale_potenziale': round(emissioni_totali_senza_pv, 1),
        'litri_totali': round(litri_totali, 1),
        'kwh_totali': round(kwh_consumati_totali, 1),
        'alberi': round(co2_risparmiata_solare / KG_CO2_ALBERO, 0),
        'labels_pie': json.dumps(['Gasolio', 'Elettricità Rete (Residua)']),
        'data_pie': json.dumps([round(co2_gasolio, 1), round(co2_rete_reale, 1)])
    }
    return render(request, 'pages/co2.html', context)

def get_filtered_df(data, date_col, val_col, request):
    """Filtra il DataFrame per date e raggruppa per frequenza"""
    if not data:
        return pd.DataFrame(), [], []

    df = pd.DataFrame(data)
    df[date_col] = pd.to_datetime(df[date_col])
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        df = df[df[date_col] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df[date_col] <= pd.to_datetime(end_date)]
    
    if df.empty:
        return df, [], []

    freq = request.GET.get('freq', 'D')
    agg_time = df.resample(freq, on=date_col)[val_col].sum().fillna(0)
    labels = [d.strftime('%Y-%m-%d') for d in agg_time.index]
    
    return df, labels, agg_time.tolist()


@login_required
def electricity_view(request):
    data = request.session.get('dati_elettrici', [])
    area = float(request.session.get('area_pannelli', 3000))
    freq = request.GET.get('freq', 'D') # Recuperiamo la frequenza (D, W, M)
    
    df, labels, values_ele_wh = get_filtered_df(data, 'Date', 'Consumption (Wh)', request)
    values_ele = [val / 1000 for val in values_ele_wh]
    values_fv = []
    for label in labels:
        dt = pd.to_datetime(label)
        m = dt.month
        if m in [12, 1, 2]: irr = 789.7
        elif m in [3, 4, 5]: irr = 2756.6
        elif m in [6, 7, 8]: irr = 5676.7
        else: irr = 2748.9
        
        prod_giornaliera = irr * area * 0.18 * 0.75 / 1000

        if freq == 'ME':
            giorni_nel_periodo = df[
                (df['Date'].dt.month == dt.month) & 
                (df['Date'].dt.year == dt.year)
            ]['Date'].dt.date.nunique()
            if giorni_nel_periodo == 0:
                giorni_nel_periodo = dt.days_in_month
        elif freq == 'W':
            giorni_nel_periodo = 7
        else:
            giorni_nel_periodo = 1
            
        values_fv.append(prod_giornaliera * giorni_nel_periodo)

    return render(request, 'pages/electricity.html', {
        'segment': 'electricity',
        'labels': json.dumps(labels),
        'values_ele': json.dumps(values_ele),
        'values_fv': json.dumps(values_fv),
        'current_freq': freq,
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'area_pannelli': area
    })


@login_required
def gas_view(request):
    data = request.session.get('dati_benzina', [])
    asset_filter = request.GET.get('asset') # Recupera il filtro dal dropdown
    asset_list = []

    if data:
        df_base = pd.DataFrame(data)
        # Estrae la lista dei veicoli per il dropdown
        asset_list = sorted(df_base['asset_name'].unique().tolist())
        
        # Applica il filtro se selezionato
        if asset_filter:
            data_to_process = df_base[df_base['asset_name'] == asset_filter].to_dict(orient='records')
        else:
            data_to_process = data
    else:
        data_to_process = []

    # Elaborazione dati filtrati per il grafico temporale
    df, labels, values_gas = get_filtered_df(data_to_process, 'reference_date', 'consumption_in_l', request)
    
    # Calcolo ripartizione per asset (Grafico a barre sempre visibile)
    labels_asset, values_asset = [], []
    if data:
        full_df = pd.DataFrame(data)
        agg_asset = full_df.groupby('asset_name')['consumption_in_l'].sum().sort_values(ascending=False)
        labels_asset = list(agg_asset.index)
        values_asset = [round(float(x), 2) for x in agg_asset.values]

    return render(request, 'pages/gas.html', {
        'segment': 'gas',
        'labels': json.dumps(labels),
        'values_gas': json.dumps(values_gas),
        'labels_asset': json.dumps(labels_asset),
        'values_asset': json.dumps(values_asset),
        'asset_list': asset_list,
        'current_asset': asset_filter,
        'current_freq': request.GET.get('freq', 'D'),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
    })


@login_required
def working_hours_view(request):
    data = request.session.get('dati_working_hours', [])
    asset_filter = request.GET.get('asset')
    asset_list = []

    if data:
        df_base = pd.DataFrame(data)
        # Lista veicoli per dropdown
        asset_list = sorted(df_base['asset_name'].unique().tolist())
        
        # Conversione secondi in ore
        df_base['hours'] = pd.to_numeric(df_base['working_time_seconds'], errors='coerce') / 3600
        
        # Filtro asset
        if asset_filter:
            df_base = df_base[df_base['asset_name'] == asset_filter]
            
        data_to_process = df_base.to_dict(orient='records')
    else:
        data_to_process = []

    # Elaborazione per grafico temporale
    df, labels, values_hours = get_filtered_df(data_to_process, 'reference_date', 'hours', request)
    
    # Riassunto per asset (Grafico a barre)
    labels_asset, values_asset = [], []
    if data:
        full_df = pd.DataFrame(data)
        full_df['hours'] = pd.to_numeric(full_df['working_time_seconds'], errors='coerce') / 3600
        agg_asset = full_df.groupby('asset_name')['hours'].sum().sort_values(ascending=False)
        labels_asset = list(agg_asset.index)
        values_asset = [round(float(x), 2) for x in agg_asset.values]

    return render(request, 'pages/working_hours.html', {
        'segment': 'working_hours',
        'labels': json.dumps(labels),
        'values_hours': json.dumps(values_hours),
        'labels_asset': json.dumps(labels_asset),
        'values_asset': json.dumps(values_asset),
        'asset_list': asset_list,
        'current_asset': asset_filter,
        'current_freq': request.GET.get('freq', 'D'),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
    })

@login_required
def tables_view(request):
    # --- LOGICA DI PULIZIA DATI ---
    if request.method == 'POST' and 'pulisci_tipo' in request.POST:
        tipo_da_pulire = request.POST.get('pulisci_tipo')
        key_map = {
            'elettrici': 'dati_elettrici', 
            'benzina': 'dati_benzina', 
            'working_hours': 'dati_working_hours'
        }
        if tipo_da_pulire in key_map:
            request.session[key_map[tipo_da_pulire]] = []
            request.session.modified = True
        return redirect('tables')

    # --- LOGICA DI CARICAMENTO ---
    if request.method == 'POST' and request.FILES.get('file_excel'):
        file = request.FILES['file_excel']
        tipo = request.POST.get('tipo_consumo')
        try:
            df = pd.read_excel(file)
            for col in df.columns:
                if df[col].dtype == 'datetime64[ns]':
                    df[col] = df[col].dt.strftime('%Y-%m-%d')
            df = df.fillna('')
            dict_data = df.to_dict(orient='records')
            
            key_map = {'elettrici': 'dati_elettrici', 'benzina': 'dati_benzina', 'working_hours': 'dati_working_hours'}
            if tipo in key_map:
                request.session[key_map[tipo]] = dict_data
            
            request.session.modified = True
            # FIX: Il redirect forza il refresh immediato dei dati a video
            return redirect('tables') 
        except Exception as e:
            print(f"Errore: {e}")
            return redirect('tables')

    # --- RESTO DELLA VIEW ---
    if request.method == 'GET':
        for param in ['area_pannelli', 'prezzo_acquisto', 'prezzo_vendita', 'prezzo_gasolio']:
            val = request.GET.get(param)
            if val not in [None, '']:
                request.session[param] = float(val)
        request.session.modified = True

    full_ele = request.session.get('dati_elettrici', [])
    full_gas = request.session.get('dati_benzina', [])
    full_wh = request.session.get('dati_working_hours', [])

    context = {
        'segment': 'tables',
        'dati_elettrici': full_ele[:5],
        'dati_benzina': full_gas[:5],
        'dati_working_hours': full_wh[:5],
        'count_ele': len(full_ele),
        'count_gas': len(full_gas),
        'count_wh': len(full_wh),
        'area_pannelli': request.session.get('area_pannelli', 3000),
        'prezzo_acquisto': request.session.get('prezzo_acquisto', 0.10),
        'prezzo_vendita': request.session.get('prezzo_vendita', 0.05),
        'prezzo_gasolio': request.session.get('prezzo_gasolio', 1.75),
    }
    return render(request, 'pages/tables.html', context)