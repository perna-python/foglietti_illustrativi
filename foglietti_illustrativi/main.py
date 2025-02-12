import httpx
import flet as ft
from dataclasses import dataclass
import subprocess
import platform
import os

@dataclass
class APIConfig:
    BASE_URL = "https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0"
    SEARCH_ENDPOINT = f"{BASE_URL}/formadosaggio/ricerca"
    DOCUMENTS_ENDPOINT = f"{BASE_URL}/organizzazione/{{codiceSis}}/farmaci/{{aic6}}/stampati"

class FileHandler:
    @staticmethod
    def open_pdf(filepath: str):
        if platform.system() == "Windows":
            os.startfile(os.path.join(os.getcwd(), filepath))
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])

class APIService:
    @staticmethod
    def search_medicines(query: str, spelling_correction: bool = True) -> dict:
        params = {
            'query': query,
            'spellingCorrection': str(spelling_correction).lower(),
            'page': '0',
        }
        response = httpx.get(APIConfig.SEARCH_ENDPOINT, params=params)
        return response.json()

    @staticmethod
    def download_document(codiceSis: str, aic6: str, doc_type: str, output_path: str):
        params = {'ts': doc_type}
        response = httpx.get(
            APIConfig.DOCUMENTS_ENDPOINT.format(codiceSis=codiceSis, aic6=aic6),
            params=params
        )
        with open(output_path, 'wb') as f:
            f.write(response.content)
        FileHandler.open_pdf(output_path)

class MedicineApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.setup_page()
        self.search_results = ft.Column(scroll='auto', height=200)
        self.detail_results = ft.Column(scroll='auto', height=400)
        self.search_field = self.create_search_field()
        self.loading = ft.ProgressBar(visible=False)
        self.init_ui()

    def setup_page(self):
        self.page.title = "Ricerca Farmaci"
        self.page.padding = 20
        self.page.theme_mode = "light"
        self.page.window_width = 1000
        self.page.window_min_width = 600
        self.page.bgcolor = "#f0f2f5"
        self.page.fonts = {
            "Roboto": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap"
        }

    def create_search_field(self) -> ft.TextField:
        return ft.TextField(
            label="Cerca farmaco",
            on_change=self.search_medicine,
            on_submit=self.search_medicine,
            autofocus=True,
            prefix_icon=ft.Icons.SEARCH,
            border_radius=10,
            filled=True,
            expand=True,
            hint_text="Inserisci il nome del farmaco...",
            text_size=16
        )

    def init_ui(self):
        header = ft.Container(
            content=ft.Column([
                ft.Text("Ricerca Farmaci", 
                       size=32, 
                       weight="bold",
                       color="#1976d2"),
                ft.Text("Cerca e consulta foglietti illustrativi", 
                       size=16, 
                       color="grey")
            ]),
            margin=ft.margin.only(bottom=20)
        )

        search_bar = ft.Container(
            content=ft.Column([
                self.search_field,
                self.loading
            ]),
            margin=ft.margin.only(bottom=20)
        )

        results_area = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Text("Suggerimenti", size=16, weight="bold"),
                    bgcolor="#ffffff",
                    padding=10,
                    border_radius=ft.border_radius.only(top_left=10, top_right=10)
                ),
                ft.Container(
                    content=self.search_results,
                    bgcolor="#ffffff",
                    padding=10,
                    border_radius=ft.border_radius.only(bottom_left=10, bottom_right=10),
                    shadow=ft.BoxShadow(
                        spread_radius=1,
                        blur_radius=10,
                        color=ft.Colors.with_opacity(0.1, "black")
                    )
                )
            ])
        )

        self.page.add(
            header,
            search_bar,
            results_area,
            ft.Container(
                content=self.detail_results,
                margin=ft.margin.only(top=20),
                height=400,  # Altezza fissa del container
                expand=True  # Permette l'espansione
            )
        )

    async def search_medicine(self, e):
        if len(self.search_field.value) > 2:
            self.loading.visible = True
            self.page.update()
            
            self.search_results.controls.clear()
            data = APIService.search_medicines(self.search_field.value)
            self.display_search_results(data)
            
            self.loading.visible = False
            self.page.update()

    def display_search_results(self, data: dict):
        for item in data.get('data', {}).get('content', []):
            display_text = f"{item['medicinale']['denominazioneMedicinale']} - {item['descrizioneFormaDosaggio']}"
            result_button = ft.TextButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.MEDICATION),
                    ft.Text(display_text, size=14)
                ]),
                on_click=lambda _, item=item: self.show_details(item),
                style=ft.ButtonStyle(
                    color="#1976d2",
                    overlay_color=ft.Colors.with_opacity(0.1, "#1976d2")
                )
            )
            self.search_results.controls.append(result_button)

    def show_details(self, item: dict):
        self.detail_results.controls.clear()
        medicinale = item['medicinale']
        codiceSis = medicinale['codiceSis']
        aic6 = medicinale['aic6']

        detail_container = self.create_detail_container(item, codiceSis, aic6)
        self.detail_results.controls.append(detail_container)
        self.page.update()

    def create_detail_container(self, item: dict, codiceSis: str, aic6: str) -> ft.Container:
        medicinale = item['medicinale']
        confezioni = item.get('confezioni', [])
        
        header_row = ft.Row(
            controls=[
                ft.Text(
                    medicinale['denominazioneMedicinale'], 
                    size=24, 
                    weight='bold',
                    color="#1976d2",
                    expand=True
                ),
                self.create_download_buttons(codiceSis, aic6)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
        details = [
            header_row,
            ft.Divider(height=2, color="#1976d2"),
            self.create_info_row(ft.Icons.MEDICATION_LIQUID, "Forma:", item['formaFarmaceutica']),
            self.create_info_row(ft.Icons.SCIENCE, "Principi attivi:", ', '.join(item['principiAttiviIt'])),
            self.create_info_row(ft.Icons.HEALING, "Via somministrazione:", ', '.join(item['vieSomministrazione'])),
            self.create_info_row(ft.Icons.CATEGORY, "Codice ATC:", ', '.join(item['codiceAtc']))
        ]
        
        for conf in confezioni:
            package_details = ft.Container(
                content=ft.Column([
                    ft.Text("Dettagli confezione", weight='bold', size=16),
                    self.create_info_row(ft.Icons.NUMBERS, "AIC:", conf['aic']),
                    self.create_info_row(ft.Icons.DESCRIPTION, "Descrizione:", conf['denominazionePackage']),
                    self.create_info_row(ft.Icons.EURO, "Classe:", f"{conf['classeRimborsabilita']} - {conf['descrizioneRimborsabilita']}"),
                    self.create_info_row(ft.Icons.INFO, "Stato:", conf['descrizioneStatoAmministrativo']),
                    self.create_info_row(ft.Icons.RECEIPT, "Prescrizione:", ', '.join(conf['descrizioneRf']))
                ]),
                bgcolor="#f8f9fa",
                padding=10,
                border_radius=10,
                margin=ft.margin.only(top=10, bottom=10)
            )
            details.append(package_details)
            
            if conf['carente']:
                shortage_info = ft.Container(
                    content=ft.Column([
                        ft.Text("⚠️ FARMACO CARENTE", color='red', weight='bold', size=16),
                        self.create_info_row(ft.Icons.CALENDAR_TODAY, "Inizio carenza:", conf['carenzaInizio']),
                        self.create_info_row(ft.Icons.EVENT, "Fine prevista:", conf['carenzaFinePresunta']),
                        self.create_info_row(ft.Icons.INFO_OUTLINE, "Motivazione:", conf['carenzaMotivazione'])
                    ]),
                    bgcolor="#fff3f3",
                    padding=10,
                    border_radius=10,
                    margin=ft.margin.only(bottom=10)
                )
                details.append(shortage_info)
        
        warnings = []
        if item['flagDopante']:
            warnings.append(("⚠️ Sostanza dopante", ft.Icons.WARNING_AMBER))
        if item['flagGuida']:
            warnings.append(("⚠️ Influenza la guida", ft.Icons.DIRECTIONS_CAR))
        if item['flagAlcol']:
            warnings.append(("⚠️ Interazione con alcol", ft.Icons.LOCAL_BAR))
        if item['flagPotassio']:
            warnings.append(("⚠️ Interazione con potassio", ft.Icons.SCIENCE))
        
        if warnings:
            warnings_container = ft.Container(
                content=ft.Column([
                    ft.Text("Avvertenze:", weight='bold', size=16),
                    *[self.create_warning_row(text, icon) for text, icon in warnings]
                ]),
                bgcolor="#fff3cd",
                padding=10,
                border_radius=10,
                margin=ft.margin.only(top=10, bottom=10)
            )
            details.append(warnings_container)
        
        
        return ft.Container(
            content=ft.Column(details),
            padding=20,
            bgcolor="white",
            border_radius=10,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=10,
                color=ft.Colors.with_opacity(0.1, "black")
            )
        )

    def create_info_row(self, icon: str, label: str, value: str) -> ft.Row:
        return ft.Row([
            ft.Icon(icon, size=20, color="#666666"),
            ft.Text(f"{label} ", weight="bold", size=14),
            ft.Text(value, size=14, selectable=True)
        ])

    def create_warning_row(self, text: str, icon: str) -> ft.Row:
        return ft.Row([
            ft.Icon(icon, color="#856404", size=20),
            ft.Text(text, color="#856404")
        ])

    def create_download_buttons(self, codiceSis: str, aic6: str) -> ft.Row:
        return ft.Row([
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.DESCRIPTION),
                    ft.Text("Foglietto Illustrativo")
                ]),
                style=ft.ButtonStyle(
                    color="white",
                    bgcolor="#1976d2",
                ),
                on_click=lambda _, c=codiceSis, a=aic6: 
                    APIService.download_document(c, a, 'FI', './foglietto.pdf')
            ),
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.SUMMARIZE),
                    ft.Text("Riassunto Caratteristiche")
                ]),
                style=ft.ButtonStyle(
                    color="white",
                    bgcolor="#388e3c",
                ),
                on_click=lambda _, c=codiceSis, a=aic6: 
                    APIService.download_document(c, a, 'RCP', './riassunto.pdf')
            )
        ])

def main(page: ft.Page):
    MedicineApp(page)

if __name__ == "__main__":
    ft.app(target=main)
