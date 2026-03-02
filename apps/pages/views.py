import pandas as pd
import json
from django.shortcuts import render

def index(request):
    # Recupero dati dalle sessioni
    ele_data = request.session.get('dati_elettrici', [])
    gas_data = request.session.get('dati_benzina', [])
    
    # Parametro per l'intervallo temporale (default 'D' = Giorni)
    # Pandas freq: 'D' (Giorno), 'ME' (Mese), 'YE' (Anno), 'H' (Ora)
    periodo = request.GET.get('period', 'D')

    # --- PARAMETRI IMPIANTO FOTOVOLTAICO (Conversione Wh/m2 -> Wh totali) ---
    AREA_PANNELLI = 100  # Modifica con i metri quadri reali del capannone
    EFFICIENZA = 0.18    # 18% efficienza media pannelli
    PR = 0.75            # Performance Ratio (perdite di sistema)
    COEFF_CONVERSIONE = AREA_PANNELLI * EFFICIENZA * PR 

    labels_ele = []
    values_ele = []
    values_prod_fv = []
    labels_work = []
    values_work = []

    # --- ELABORAZIONE ELETTRICITÀ E FOTOVOLTAICO ---
    if ele_data:
        df_ele = pd.DataFrame(ele_data)
        df_ele['Date'] = pd.to_datetime(df_ele['Date'])
        
        # Aggregazione temporale dinamica
        agg_ele = df_ele.resample(periodo, on='Date')['Consumption (Wh)'].sum()
        labels_ele = [d.strftime('%Y-%m-%d') for d in agg_ele.index]
        values_ele = agg_ele.tolist()

        # Calcolo Produzione Reale Stimata in Wh (Dati Dario per Pratolino)
        def get_production_wh(d):
            m = d.month
            # Valori stimati Wh/m2 forniti da Dario
            if m in [12, 1, 2]: irraggiamento = 789.7   # Inverno
            elif m in [3, 4, 5]: irraggiamento = 2756.6 # Primavera
            elif m in [6, 7, 8]: irraggiamento = 5676.7 # Estate
            else: irraggiamento = 2748.9                # Autunno
            
            # Conversione finale in Wh totali per il grafico
            return irraggiamento * COEFF_CONVERSIONE
        
        values_prod_fv = [get_production_wh(d) for d in agg_ele.index]

    # --- ELABORAZIONE WORKING HOURS (Dati Asset Mezzi) ---
    if gas_data:
        df_gas = pd.DataFrame(gas_data)
        # Contiamo le occorrenze di ogni asset come proxy delle ore di lavoro
        work_agg = df_gas.groupby('asset_name').size() 
        labels_work = list(work_agg.index)
        values_work = [float(x) for x in work_agg.values]

    context = {
        'segment': 'index',
        'periodo_attivo': periodo,
        'labels_ele': json.dumps(labels_ele),
        'values_ele': json.dumps(values_ele),
        'values_fv': json.dumps(values_prod_fv),
        'labels_work': json.dumps(labels_work),
        'values_work': json.dumps(values_work),
    }
    return render(request, 'pages/index3.html', context)

def tables_view(request):
    dati_elettrici = request.session.get('dati_elettrici', [])
    dati_benzina = request.session.get('dati_benzina', [])

    if request.method == 'POST' and request.FILES.get('file_excel'):
        file = request.FILES['file_excel']
        tipo = request.POST.get('tipo_consumo')
        try:
            df = pd.read_excel(file)
            
            # Formattazione date e pulizia per serializzazione JSON
            for col in df.columns:
                if df[col].dtype == 'datetime64[ns]':
                    df[col] = df[col].dt.strftime('%Y-%m-%d')
            
            df = df.fillna('')
            dict_data = df.to_dict(orient='records')

            if tipo == 'elettrici':
                request.session['dati_elettrici'] = dict_data
            else:
                request.session['dati_benzina'] = dict_data
                
            request.session.modified = True
        except Exception as e:
            print(f"Errore caricamento Excel: {e}")

    return render(request, 'pages/tables.html', {
        'segment': 'tables',
        'dati_elettrici': dati_elettrici,
        'dati_benzina': dati_benzina,
    })