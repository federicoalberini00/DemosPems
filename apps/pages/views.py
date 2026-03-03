import pandas as pd
import json
from django.shortcuts import render
import numpy as np
from django.contrib.auth.decorators import login_required

@login_required
def economic_view(request):
    # Recupero dati dalle sessioni
    data_ele = request.session.get('dati_elettrici', [])
    data_gas = request.session.get('dati_benzina', [])
    
    # --- 1. GESTIONE INPUT E SESSIONE (Persistenza parametri) ---
    area_input = request.session.get('area_pannelli', 3000)
    acquisto_input = request.session.get('prezzo_acquisto', 0.10)
    vendita_input = request.session.get('prezzo_vendita', 0.05)
    gasolio_input = request.session.get('prezzo_gasolio', 1.75)

    # Logica AREA
    if area_input not in [None, '']:
        area = float(area_input)
        request.session['area_pannelli'] = area
    else:
        area = request.session.get('area_pannelli', 3000)

    # Logica PREZZO ACQUISTO ENERGIA
    if acquisto_input not in [None, '']:
        prezzo_acquisto = float(acquisto_input)
        request.session['prezzo_acquisto'] = prezzo_acquisto
    else:
        prezzo_acquisto = request.session.get('prezzo_acquisto', 0.10)

    # Logica PREZZO VENDITA ENERGIA
    if vendita_input not in [None, '']:
        prezzo_vendita = float(vendita_input)
        request.session['prezzo_vendita'] = prezzo_vendita
    else:
        prezzo_vendita = request.session.get('prezzo_vendita', 0.05)

    # Logica PREZZO GASOLIO
    if gasolio_input not in [None, '']:
        prezzo_gasolio = float(gasolio_input)
        request.session['prezzo_gasolio'] = prezzo_gasolio
    else:
        prezzo_gasolio = request.session.get('prezzo_gasolio', 1.75)

    request.session.modified = True

    # --- 2. CALCOLO GASOLIO ---
    total_gas_liters = 0
    total_gas_cost = 0
    if data_gas:
        df_gas = pd.DataFrame(data_gas)
        # Somma della colonna litri gestendo eventuali valori non numerici
        total_gas_liters = pd.to_numeric(df_gas['consumption_in_l'], errors='coerce').sum()
        total_gas_cost = total_gas_liters * prezzo_gasolio

    # Se non ci sono dati elettrici, mostriamo comunque la pagina con i KPI del gasolio
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

    # --- 3. ELABORAZIONE DATI ELETTRICI ---
    df = pd.DataFrame(data_ele)
    df['Date'] = pd.to_datetime(df['Date'])
    
    # Raggruppamento Giornaliero per totali reali
    daily_df = df.groupby(df['Date'].dt.date).agg({'Consumption (Wh)': 'sum'}).reset_index()
    daily_df['Date'] = pd.to_datetime(daily_df['Date'])
    
    hours = list(range(24))
    
    def get_solar_h(daily_total):
        curve = [max(0, np.sin((h-6)*np.pi/14)) if 6 <= h <= 20 else 0 for h in hours]
        factor = daily_total / sum(curve) if sum(curve) > 0 else 0
        return [float(c * factor) for c in curve]

    def get_cons_h(daily_total):
        base = (daily_total * 0.20) / 24
        work = (daily_total * 0.80) / 10
        return [float(work + base if 8 <= h <= 18 else base) for h in hours]

    def get_irr(m):
        # Dati irraggiamento Dario
        if m in [12, 1, 2]: return 789.7
        if m in [3, 4, 5]: return 2756.6
        if m in [6, 7, 8]: return 5676.7
        return 2748.9

    # --- 4. CALCOLO ECONOMICO ELETTRICO ---
    total_cost_period = 0
    total_gain_period = 0
    EFF, PR = 0.18, 0.75

    for _, row in daily_df.iterrows():
        d_solar = get_irr(row['Date'].month) * area * EFF * PR
        d_cons = row['Consumption (Wh)']
        s_profile = get_solar_h(d_solar)
        c_profile = get_cons_h(d_cons)
        
        for s, c in zip(s_profile, c_profile):
            if s > c: 
                total_gain_period += ((s - c) / 1000) * prezzo_vendita
            else: 
                total_cost_period += ((c - s) / 1000) * prezzo_acquisto

    # --- 5. PREPARAZIONE GRAFICI ---
    daily_df['Stagione'] = daily_df['Date'].dt.month.map(lambda m: 
        'Inverno' if m in [12,1,2] else 'Primavera' if m in [3,4,5] else 'Estate' if m in [6,7,8] else 'Autunno')
    
    seasonal_stats = daily_df.groupby('Stagione')['Consumption (Wh)'].mean()
    stagioni_list = ['Inverno', 'Primavera', 'Estate', 'Autunno']
    typical_days = {}

    for stag in stagioni_list:
        media_c = seasonal_stats.get(stag, 0)
        m_ref = {'Inverno': 1, 'Primavera': 4, 'Estate': 7, 'Autunno': 10}[stag]
        teorico_s = get_irr(m_ref) * area * EFF * PR
        typical_days[stag] = {
            'solar': get_solar_h(teorico_s),
            'cons': get_cons_h(media_c)
        }

    context = {
        'segment': 'economic',
        'stagioni_list': stagioni_list,
        'seasonal_labels': json.dumps(stagioni_list),
        'seasonal_cons': json.dumps([float(seasonal_stats.get(s, 0)) for s in stagioni_list]),
        'seasonal_prod': json.dumps([float(get_irr({'Inverno': 1, 'Primavera': 4, 'Estate': 7, 'Autunno': 10}[s]) * area * EFF * PR) for s in stagioni_list]),
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

    # --- 1. GASOLIO ---
    litri_totali = 0
    if data_gas:
        df_gas = pd.DataFrame(data_gas)
        litri_totali = pd.to_numeric(df_gas['consumption_in_l'], errors='coerce').sum()
    co2_gasolio = litri_totali * KG_CO2_LITRO

    # --- 2. ELETTRICITÀ ---
    co2_rete_reale = 0          # Quello che emetti davvero oggi (prelievo notturno/picchi)
    co2_potenziale_senza_pv = 0 # Quello che emetteresti senza pannelli
    co2_risparmiata_solare = 0  # Il beneficio totale del sole
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
            
            # 1. Emissioni Potenziali: se non avessi il PV, emetteresti tutto questo
            co2_potenziale_senza_pv += (cons_gg / 1000) * KG_CO2_KWH
            kwh_consumati_totali += cons_gg / 1000
            
            s_prof = get_solar_h(prod_gg)
            c_prof = get_cons_h(cons_gg)
            
            for s, c in zip(s_prof, c_prof):
                if c > s:
                    # 2. Emissioni Reali: solo la parte non coperta dal sole
                    co2_rete_reale += ((c - s) / 1000) * KG_CO2_KWH
                
                # 3. Risparmio Solare Totale
                co2_risparmiata_solare += (s / 1000) * KG_CO2_KWH

    # Calcolo totale "Senza Impianto" vs "Con Impianto"
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
    
    # 1. Filtro Intervallo Date
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    if start_date:
        df = df[df[date_col] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df[date_col] <= pd.to_datetime(end_date)]
    
    if df.empty:
        return df, [], []

    # 2. Raggruppamento Temporale
    freq = request.GET.get('freq', 'D')
    agg_time = df.resample(freq, on=date_col)[val_col].sum().fillna(0)
    labels = [d.strftime('%Y-%m-%d') for d in agg_time.index]
    
    return df, labels, agg_time.tolist()

# --- 1. VISTA ELETTRICITÀ ---

@login_required
def electricity_view(request):
    data = request.session.get('dati_elettrici', [])
    area = float(request.GET.get('area_pannelli', 100))
    df, labels, values_ele = get_filtered_df(data, 'Date', 'Consumption (Wh)', request)
    
    values_fv = []
    for label in labels:
        m = pd.to_datetime(label).month
        if m in [12, 1, 2]: irr = 789.7
        elif m in [3, 4, 5]: irr = 2756.6
        elif m in [6, 7, 8]: irr = 5676.7
        else: irr = 2748.9
        # Wh = irr * area * eff * pr
        values_fv.append(irr * area * 0.18 * 0.75)

    return render(request, 'pages/electricity.html', {
        'segment': 'electricity',
        'labels': json.dumps(labels),
        'values_ele': json.dumps(values_ele),
        'values_fv': json.dumps(values_fv),
        'current_freq': request.GET.get('freq', 'D'),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'area_pannelli': area
    })

# --- 2. VISTA GASOLIO ---

@login_required
def gas_view(request):
    data = request.session.get('dati_benzina', [])
    df, labels, values_gas = get_filtered_df(data, 'reference_date', 'consumption_in_l', request)
    
    labels_asset, values_asset = [], []
    if not df.empty:
        agg_asset = df.groupby('asset_name')['consumption_in_l'].sum().sort_values(ascending=False)
        labels_asset = list(agg_asset.index)
        values_asset = [round(float(x), 2) for x in agg_asset.values]

    return render(request, 'pages/gas.html', {
        'segment': 'gas',
        'labels': json.dumps(labels),
        'values_gas': json.dumps(values_gas),
        'labels_asset': json.dumps(labels_asset),
        'values_asset': json.dumps(values_asset),
        'current_freq': request.GET.get('freq', 'D'),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
    })

# --- 3. VISTA WORKING HOURS ---

@login_required
def working_hours_view(request):
    data = request.session.get('dati_working_hours', [])
    # Preparazione ore prima del filtro
    if data:
        df_base = pd.DataFrame(data)
        df_base['hours'] = pd.to_numeric(df_base['working_time_seconds'], errors='coerce') / 3600
        data = df_base.to_dict(orient='records')

    df, labels, values_hours = get_filtered_df(data, 'reference_date', 'hours', request)
    
    labels_asset, values_asset = [], []
    if not df.empty:
        agg_asset = df.groupby('asset_name')['hours'].sum().sort_values(ascending=False)
        labels_asset = list(agg_asset.index)
        values_asset = [round(float(x), 2) for x in agg_asset.values]

    return render(request, 'pages/working_hours.html', {
        'segment': 'working_hours',
        'labels': json.dumps(labels),
        'values_hours': json.dumps(values_hours),
        'labels_asset': json.dumps(labels_asset),
        'values_asset': json.dumps(values_asset),
        'current_freq': request.GET.get('freq', 'D'),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
    })

@login_required
def tables_view(request):
    # Recupero dati completi dalle sessioni
    full_ele = request.session.get('dati_elettrici', [])
    full_gas = request.session.get('dati_benzina', [])
    full_wh = request.session.get('dati_working_hours', [])

    # --- GESTIONE PARAMETRI ECONOMICI (GET) ---
    if request.method == 'GET':
        for param in ['area_pannelli', 'prezzo_acquisto', 'prezzo_vendita', 'prezzo_gasolio']:
            val = request.GET.get(param)
            if val not in [None, '']:
                request.session[param] = float(val)
        request.session.modified = True

    # --- CARICAMENTO EXCEL (POST) ---
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
            # Ricarichiamo i dati appena salvati per la preview
            return redirect('tables') # Assicurati che il nome della url sia 'tables'
        except Exception as e:
            print(f"Errore: {e}")

    # --- LOGICA LIGHT: Slicing per il template ---
    context = {
        'segment': 'tables',
        'dati_elettrici': full_ele[:5],  # Solo 5 righe per la velocità
        'dati_benzina': full_gas[:5],    # Solo 5 righe per la velocità
        'dati_working_hours': full_wh[:5],# Solo 5 righe per la velocità
        'count_ele': len(full_ele),
        'count_gas': len(full_gas),
        'count_wh': len(full_wh),
        'area_pannelli': request.session.get('area_pannelli', 3000),
        'prezzo_acquisto': request.session.get('prezzo_acquisto', 0.10),
        'prezzo_vendita': request.session.get('prezzo_vendita', 0.05),
        'prezzo_gasolio': request.session.get('prezzo_gasolio', 1.75),
    }
    return render(request, 'pages/tables.html', context)