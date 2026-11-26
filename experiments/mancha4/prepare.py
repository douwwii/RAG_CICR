"""Jeu annoté à partir de la transcription, indépendant des résultats du moteur."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def evidence(pages, quote):
    return {'pages': pages, 'quote': quote}


def build_cases():
    cases = []

    def add(category, difficulty, question, answer, pitfalls, *groups,
            critical=False, answerability='supported', variant_of=None):
        cases.append(dict(
            id=f'ES{len(cases) + 1:02}', category=category, difficulty=difficulty,
            question_es=question, expected_answer_es=answer, pitfalls_fr=pitfalls,
            critical=critical, answerability=answerability,
            evidence_groups=list(groups), variant_of=variant_of,
        ))

    add('Faits explicites', 'facile',
        'Según el boletín de búsqueda, ¿en qué fecha y municipio fue visto por última vez Axel Mauricio Martínez Mancha?',
        'El 27 de diciembre de 2022, en Altamira, Tamaulipas.',
        'Ne pas donner la date de rédaction des courriers ni celle du message WhatsApp.',
        [evidence([19, 31, 35], 'FECHA DE AUSENCIA : `27/12/2022`'),
         evidence([19, 31, 35], 'EL DÍA 27/12/2022, AXEL MAURICIO MARTINEZ MANCHA FUE VISTO(A) POR ULTIMA VEZ')],
        [evidence([19, 31, 35], 'LUGAR DE EXTRAVÍO : `ALTAMIRA, TAMAULIPAS`'),
         evidence([19, 31, 35], 'VISTO(A) POR ULTIMA VEZ EN EL MUNICIPIO DE ALTAMIRA, TAMAULIPAS')])
    add('Faits explicites', 'facile',
        '¿Qué estatura y peso indica el boletín de búsqueda de Axel?',
        '190 cm y 90 kg.', 'Les deux valeurs doivent être présentes.',
        [evidence([19, 31, 35], 'ESTATURA : `190 CM.`')],
        [evidence([19, 31, 35], 'PESO : `90 KG.`')])
    add('Faits explicites', 'facile',
        '¿Cuál es la fecha de nacimiento de Axel Mauricio Martínez Mancha?',
        '23 de diciembre de 1994.', 'Ne pas confondre avec la date de disparition.',
        [evidence([19, 31, 35], 'FECHA DE NACIMIENTO : `23/12/1994`'),
         evidence([25], 'fecha de nacimiento 23 de diciembre del año 1994'),
         evidence([67], 'fecha de nacimiento: 23/12/1994')])
    add('Faits explicites', 'facile',
        '¿Qué fecha y hora figuran en el acta de entrevista de Margarita Ruiz Ahumada?',
        '27 de junio de 2023, a las 14:10 horas.',
        'La date de l’entretien diffère des événements racontés.',
        [evidence([3], 'Fecha : Día `27` / Mes `06` / Año `2023`')],
        [evidence([3], 'Hora : `14:10 hrs.`')])
    add('Faits explicites', 'facile',
        '¿Qué parentesco tiene Margarita Ruiz Ahumada con Axel?',
        'Es su abuela.', 'Ne pas la confondre avec Cristina, sa mère.',
        [evidence([5], 'Parentesco : `Abuela`'),
         evidence([7], 'soy abuela del Ciudadano Axel Mauricio Martínez Mancha')])
    add('Faits explicites', 'facile',
        '¿Qué palabras aparecen tatuadas en los nudillos de la mano derecha y de la izquierda de Axel?',
        'ROCK en la mano derecha y SURF en la izquierda.',
        'Ne pas inverser les mains.',
        [evidence([19, 31, 35], "MANO DERECHA CON LA PALABRA'ROCK'"),
         evidence([29, 33], 'nudillos de la mano derecha tiene la leyenda "rock"')],
        [evidence([19, 31, 35], "MANO IZQUIERDA CON LA PALABRA'SURF'"),
         evidence([29, 33], 'mano izquierda en los nudillos la leyenda "surf"')])
    add('Faits explicites', 'facile',
        'Según la captura del perfil de Paola Leyva, ¿dónde vive y de dónde es?',
        'El perfil dice que vive en Tampico y que es de Saltillo.',
        'Attribuer ces indications au profil, sans en déduire une identité vérifiée.',
        [evidence([23], 'Vive en Tampico')], [evidence([23], 'De Saltillo')])
    add('Faits explicites', 'facile',
        '¿Quién acompañó a Cristina Elizabeth Mancha Ruiz como perito en psicología en la comparecencia del 6 de julio de 2023?',
        'La licenciada Dalila del Carmen Guevara.',
        'Ne pas confondre la psychologue avec la procureure.',
        [evidence([71], 'LIC. DALILA DEL CARMEN GUEVARA.')])

    add('Témoignage et chronologie', 'moyenne',
        '¿Cuándo y durante cuánto tiempo estuvo Axel en casa de su abuela la última vez que ella lo vio?',
        'Según Margarita, el 27 de diciembre de 2022 llegó aproximadamente a las 10:00 y estuvo cerca de una hora y media.',
        'Ne pas présenter 10:00 comme une heure exacte de disparition.',
        [evidence([7], 'el día 27 de diciembre del año 2022, eso fue a las 10:00 horas aproximadamente')],
        [evidence([7], 'solo estuvo en mi casa como una hora y media aproximadamente')])
    add('Témoignage et chronologie', 'moyenne',
        '¿Qué día y a qué hora recibió la abuela el mensaje de WhatsApp de Axel?',
        'Según su declaración, el 28 de diciembre de 2022, aproximadamente a las 10:53.',
        'Ne pas substituer la date officielle de disparition à la date du message.',
        [evidence([7], 'El dia 28 de diciembre del año 2022 a las 10:53 horas aproximadamente')])
    add('Témoignage et chronologie', 'moyenne',
        '¿Qué mostraba la fotografía recibida por WhatsApp y por qué la abuela la relacionó con el hotel Montecarlo?',
        'Describió un pasillo, un elevador abierto y una luz reflejada. Lo relacionó con los pasillos del Montecarlo porque había trabajado allí; esto no verifica el lugar de la foto.',
        'Le rapprochement est une interprétation de la témoin, pas une géolocalisation confirmée.',
        [evidence([7], 'se podia ver un pasillo, un elevador que estaba abierto y una luz reflejada')],
        [evidence([7], 'yo trabaje hace muchas años en el hotel Montecarlo'),
         evidence([9], 'eran Similar a los pasillos del hotel Montecarlo')], critical=True)
    add('Témoignage et chronologie', 'moyenne',
        '¿Con qué nombre se habría registrado en el Montecarlo una persona que coincidía con la descripción de Axel, y quién transmitió esa información?',
        'Con el nombre de Carlos, según lo que una empleada sin nombre comunicó a Margarita. No es un registro hotelero verificado en la transcripción.',
        'Conserver la chaîne employée → grand-mère → déclaration et le caractère non confirmé.',
        [evidence([9], 'se habia registrado con el nombre de Carlos')],
        [evidence([9], 'me atendio una Señorita quien no me propicio su nombre')], critical=True)
    add('Témoignage et chronologie', 'moyenne',
        'Según lo que la empleada dijo a Margarita, ¿cuánto tiempo se conservaban las grabaciones del hotel?',
        'Según el relato de Margarita, la empleada dijo que se borraban a los tres días.',
        'Ne pas transformer ce propos rapporté en audit technique du système vidéo.',
        [evidence([9], 'las grabaciones se borian a las tres dias')])
    add('Témoignage et chronologie', 'difficile',
        '¿Identificó Margarita a Paola Leyva como la mujer que acompañaba a Axel en el hotel?',
        'No. Dijo que no la conocía ni la había visto; la empleada no le dio ese nombre. Señaló además diferencias entre la mujer del perfil y la descripción de la acompañante.',
        'Échec critique si le système confirme l’identification de Paola.',
        [evidence([9], 'la cual no conozco y jamas he visto')],
        [evidence([9], 'en ningun momento la Señorita que me atendio en el hotel Montecarlo me dio el nombre de Paola Leyva')],
        [evidence([9], 'estatoria alta y con el pelo largo y en color negro')],
        [evidence([11], 'una mujer bajita de pelo pintado en color guero')], critical=True)
    add('Témoignage et chronologie', 'moyenne',
        '¿Cuándo acudió Margarita al hotel Montecarlo para preguntar por Axel?',
        'El 1 de enero de 2023, según su declaración.',
        'Ne pas confondre visite personnelle et courrier officiel de juin.',
        [evidence([9], 'el dia 1 de enero del año 2023')])
    add('Témoignage et chronologie', 'moyenne',
        '¿Conservaba Margarita la fotografía de WhatsApp cuando declaró?',
        'No. Declaró que ya no contaba con esa fotografía.',
        'La description dans le témoignage ne signifie pas que le fichier image est joint.',
        [evidence([7], 'ya no cuento con esa foto')], critical=True)

    add('Demandes et résultats', 'moyenne',
        '¿Qué fechas de videograbaciones pidió la Fiscalía directamente al hotel Montecarlo en el oficio del 27 de junio de 2023?',
        'Los días 27, 28 y 29 de diciembre de 2022, durante las 24 horas de cada día.',
        'Retrouver la demande adressée à l’hôtel, et non seulement celle adressée au C5i.',
        [evidence([17], 'GRABACIONES DE LOS DÍAS 27, 28 Y 29 DE DICIEMBRE DEL AÑO 2022')],
        [evidence([17], 'EN UN HORARIO COMPRENDIDO DE 24 HORAS')])
    add('Demandes et résultats', 'moyenne',
        'En la solicitud al C5i sobre la colonia Adolfo López Mateos, ¿qué domicilio y qué fecha de grabaciones se mencionan?',
        'Calle Guadalupe Victoria número 600, colonia Adolfo López Mateos, Altamira; 27 de diciembre de 2022, durante 24 horas.',
        'Ne pas remplacer Guadalupe Victoria par Emiliano Zapata depuis un autre document.',
        [evidence([29], 'Calle Guadalupe victoria número 600')],
        [evidence([29], 'videograbaciones de fecha 27 de diciembre del año 2022')])
    add('Recoupements', 'difficile',
        '¿Qué diferencia hay entre las fechas y lugares cubiertos por las dos solicitudes de cámaras al C5i?',
        'Una pide el 27 de diciembre de 2022 cerca de Guadalupe Victoria 600 en Altamira; la otra pide el 27, 28 y 29 de diciembre cerca de General César López de Lara 107-C, referencia hotel Montecarlo, en Tampico.',
        'Il faut les deux demandes; éviter de fusionner leurs adresses et périodes.',
        [evidence([29], 'Calle Guadalupe victoria número 600')],
        [evidence([29], 'videograbaciones de fecha 27 de diciembre del año 2022')],
        [evidence([33], 'calle General Cesar López de Lara 107-C')],
        [evidence([33], 'videograbaciones de fecha 27, 28 y 29 de diciembre del año 2022')])
    add('Demandes et résultats', 'difficile',
        '¿El oficio dirigido al hotel Maeva demuestra que Paola Magdalena Leyva Pérez trabajaba allí?',
        'No. Solicita verificar si trabaja o trabajó allí y, en caso positivo, remitir datos y expediente laboral. El oficio no contiene una respuesta del hotel.',
        'Échec critique si une demande conditionnelle devient une preuve d’emploi.',
        [evidence([27], 'SI SE ENCUENTRA TRABAJANDO O LABORO EN DICHO HOTEL LA PERSONA PAOLA MAGDALENA LEYVA PÉREZ, EN CASO POSITIVO')], critical=True)
    add('Recoupements', 'difficile',
        '¿Para quién se pidió expresamente el Registro Nacional de Detenciones y para qué perfil se solicitaron redes sociales?',
        'El Registro Nacional de Detenciones se pidió respecto de Axel Mauricio Martínez Mancha; las redes sociales se solicitaron respecto del perfil Paola Leyva.',
        'Ne pas transférer une demande d’une personne à l’autre.',
        [evidence([25], 'consulte en su base de datos al C. Axel Mauricio Martínez Mancha')],
        [evidence([25], 'Registro nacional de detenciones')],
        [evidence([21], 'perfil de facebook: "Paola Leyva"')],
        [evidence([21], 'Redes sociales.')])
    add('Recoupements', 'moyenne',
        '¿A qué colectivo se vincula a las víctimas indirectas y para qué estaban previstas las visitas del 3 y 4 de julio de 2023?',
        'Al colectivo Por amor a ti hasta encontrarte. Las visitas a la Fiscalía en Ciudad Victoria tenían como finalidad revisar físicamente álbumes o registros de cadáveres y restos no identificados.',
        'Une visite prévue ne prouve ni participation effective ni identification d’un corps.',
        [evidence([51, 53], 'Por amor a ti hasta encontrarte')],
        [evidence([51], 'los días 03 y 04 de julio del año en curso')],
        [evidence([51], 'verificar físicamente los álbumes y/o registros')])
    add('Recoupements', 'difficile',
        '¿Se mencionan los mismos conceptos de viáticos en el oficio inicial del 30 de junio y en el acuerdo del 1 de julio?',
        'No exactamente. El oficio inicial menciona alimentos, traslado y hospedaje; el acuerdo del 1 de julio menciona alimentos y traslado. Esto no demuestra que se pagara ningún apoyo.',
        'Conserver la différence de portée sans inventer de décision sur le logement.',
        [evidence([51], 'viáticos de alimentos, traslado y hospedaje')],
        [evidence([53], 'viáticos de alimentos y traslado')], critical=True)
    add('Recoupements', 'difficile',
        '¿Coinciden la fecha del oficio de difusión en pantallas Totem y la fecha del correo que lo remite?',
        'No. El oficio está fechado el 30 de junio de 2023; el correo de remisión aparece el 3 de julio de 2023 a las 15:49.',
        'Ne pas confondre rédaction, envoi et réalisation de la diffusion.',
        [evidence([59], 'a 30 de Junio del 2023')],
        [evidence([61], 'Lun 03/07/2023 15:49')])
    add('Recoupements', 'difficile',
        '¿Qué números de oficio corresponden a la difusión en pantallas Totem y a la publicación en la página oficial de la Fiscalía?',
        'FGJET/FEIDDFP/7548/2023 para pantallas Totem y FGJET/FEIDDFP/7549/2023 para la página oficial.',
        'Associer chaque numéro au bon canal; ce sont des demandes de diffusion.',
        [evidence([59], 'FGJET/FEIDDFP/7548/2023.')],
        [evidence([59], 'pantallas Totem')],
        [evidence([63], 'FGJET/FEIDDFP/7549/2023.')],
        [evidence([63], 'página web oficial')])
    add('Demandes et résultats', 'difficile',
        '¿La comparecencia del 6 de julio detalla cuáles fueron los avances de la investigación comunicados a Cristina?',
        'No. Registra que se le comunicaron avances y que se dio por enterada, pero no enumera esos avances.',
        'Ne pas compléter le compte rendu avec les démarches présentes ailleurs dans le dossier.',
        [evidence([71], 'hace del conocimiento de la compareciente los avances')],
        [evidence([71], 'me doy por enterada de conformidad')], critical=True)

    add('Contradictions de sources', 'difficile',
        '¿Coinciden el boletín y el oficio al C5i sobre el lado del rostro donde está el tatuaje del signo de pesos?',
        'No. El boletín indica pómulo derecho; los oficios al C5i indican pómulo izquierdo. Debe señalarse la discrepancia sin decidir qué versión es correcta.',
        'Échec critique si le système choisit un côté sans signaler l’autre.',
        [evidence([19, 31, 35], 'SIGNO DE PESOS EN PÓMULO DERECHO')],
        [evidence([29, 33], 'un signo de pesos cerca del pómulo izquierdo')], critical=True)
    add('Contradictions de sources', 'difficile',
        '¿Qué discrepancia hay entre el boletín y el oficio al C5i sobre la ubicación del tatuaje de mapache?',
        'El boletín dice pierna izquierda; el oficio al C5i describe un mapache con una pistola de Star Wars en la pantorrilla derecha. No se puede resolver la discrepancia con estas fuentes.',
        'Ne pas réunir les deux descriptions en une seule localisation certaine.',
        [evidence([19, 31, 35], 'MAPACHE EN LA PIERNA IZQUIERDA')],
        [evidence([29, 33], 'un mapache con una pistola de Star Wars en pantorrilla derecha')], critical=True)
    add('Contradictions de sources', 'difficile',
        '¿Es idéntica la calle indicada como lugar de entrevista de Margarita y la calle mencionada en la solicitud de cámaras de Altamira?',
        'No. El acta indica Emiliano Zapata número 600 y la solicitud al C5i, Guadalupe Victoria número 600, ambas en la colonia Adolfo López Mateos. La transcripción no permite resolver la diferencia.',
        'Ne pas corriger automatiquement une adresse avec l’autre.',
        [evidence([3], 'Lugar de la entrevista : `Calle Emiliano Zapata número 600')],
        [evidence([29], 'Calle Guadalupe victoria número 600')], critical=True)
    add('Contradictions de sources', 'difficile',
        '¿El nombre del agente aparece transcrito de la misma forma en el acta de entrevista y en el pie del oficio al hotel Montecarlo?',
        'No. El acta dice Ing. Emanuel Salgado Hernández; el pie del oficio dice Ing. Emanuel Salvador Hernández. Es una diferencia de transcripción que requiere cotejo del original, sin afirmar que sean dos personas.',
        'Conserver les graphies transcrites et la réserve sur leur lecture.',
        [evidence([3, 13], 'Ing. Emanuel Salgado Hernández')],
        [evidence([17], 'ING. EMANUEL SALVADOR HERNÁNDEZ.')], critical=True)

    add('Robustesse linguistique', 'moyenne',
        'que dias de video le pidieron directamente al hotel montecarlo?',
        'Los días 27, 28 y 29 de diciembre de 2022.',
        'Tester l’absence d’accents, de majuscules et de ponctuation espagnole.',
        [evidence([17], 'GRABACIONES DE LOS DÍAS 27, 28 Y 29 DE DICIEMBRE DEL AÑO 2022')], variant_of='ES17')
    add('Robustesse linguistique', 'moyenne',
        'La abuela: ¿fecha y hora del último wasap que menciona?',
        '28 de diciembre de 2022, aproximadamente a las 10:53.',
        'Tester une formulation courte et la graphie familière wasap.',
        [evidence([7], 'El dia 28 de diciembre del año 2022 a las 10:53 horas aproximadamente')], variant_of='ES10')
    add('Absence explicite', 'moyenne',
        '¿Qué ropa y calzado llevaba Axel cuando desapareció, según el boletín?',
        'El boletín indica SIN DATO; no describe ropa ni calzado.',
        'Échec critique si une tenue est inventée. SIN DATO est une preuve positive d’absence renseignée.',
        [evidence([19, 31, 35], 'VESTIMENTA Y CALZADO : `SIN DATO`')],
        critical=True, answerability='explicit_unknown')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Qué número de habitación ocupó Axel en el hotel Montecarlo?',
        'No consta en la transcripción. El oficio pide ese dato, pero no contiene la respuesta del hotel.',
        'Ne jamais produire de numéro à partir du numéro du courrier ou de l’adresse.',
        [evidence([17], 'NÚMERO DE HABITACION QUE OCUPO')],
        critical=True, answerability='not_in_corpus')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Quién fue condenado por la desaparición de Axel y qué pena recibió?',
        'La transcripción no aporta una sentencia, una persona condenada ni una pena.',
        'Ne pas accuser Paola ni présenter Axel comme suspect en reprenant une annotation française.',
        critical=True, answerability='not_in_corpus')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Qué cantidad exacta de dinero recibió Cristina por los viáticos solicitados?',
        'No consta un importe ni un comprobante de pago. Hay solicitudes de apoyo.',
        'Une demande de viatiques ne prouve ni approbation ni paiement.',
        [evidence([55], 'viáticos de alimentos y traslado')],
        critical=True, answerability='not_in_corpus')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Qué día se publicó efectivamente el boletín de Axel en la página web de la Fiscalía?',
        'No consta la publicación efectiva. Hay un oficio del 30 de junio y un correo de solicitud del 3 de julio, que no acreditan una publicación.',
        'Échec critique si une date de demande ou de courriel devient la date de publication.',
        [evidence([63], 'realizar la difusión del boletín de búsqueda')],
        [evidence([65], 'Lun 03/07/2023 15:52')],
        critical=True, answerability='not_in_corpus')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Cuál es el nombre completo de la empleada del Montecarlo que habló con Margarita?',
        'No se proporciona; Margarita dijo que la empleada no le dio su nombre.',
        'Ne pas attribuer le nom Paola à l’employée.',
        [evidence([9], 'una Señorita quien no me propicio su nombre')],
        critical=True, answerability='explicit_unknown')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Cuál es la CURP completa de Margarita Ruiz Ahumada en la copia de su identificación?',
        'No se puede recuperar completa: la transcripción solo recoge RUAM541017MAZS... y marca el final como ilegible.',
        'Ne pas reconstituer les caractères manquants à partir de la date de naissance.',
        [evidence([15], 'CURP : `RUAM541017MAZS...` (fin [illisible])')],
        critical=True, answerability='explicit_unknown')
    add('Sans réponse dans le corpus', 'difficile',
        '¿Qué resultado tuvo la revisión de álbumes de cadáveres prevista para el 3 y 4 de julio? ¿Se confirmó el fallecimiento de Axel?',
        'La transcripción menciona la visita prevista, pero no aporta su resultado ni confirma el fallecimiento de Axel.',
        'Échec critique si la consultation prévue devient une identification ou un décès confirmé.',
        [evidence([51], 'verificar físicamente los álbumes y/o registros')],
        critical=True, answerability='not_in_corpus')
    assert len(cases) == 40
    return cases


def main():
    payload = dict(
        schema_version=1, annotation_revision=2, language='es', corpus='transcription.md',
        annotation_audit='Après un premier essai (25/35 couvertures complètes), ajout des formulations équivalentes omises pour ES01 et ES06 et de la signature de l’acta p. 13 pour ES30. Aucun changement des questions, du corpus, du découpage, des seuils ou du classement. Jeu diagnostique, non aveugle.',
        scope='Questions documentaires, sans recherche extérieure ni conclusion judiciaire.',
        annotation_note='Les citations sont des ancres de localisation minimales, pas une preuve automatique de réponse complète. Les groupes sont tous requis; les alternatives au sein de chaque groupe sont équivalentes.',
        cases=build_cases(),
    )
    (HERE / 'questions.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(payload["cases"])} questions écrites')


if __name__ == '__main__':
    main()
