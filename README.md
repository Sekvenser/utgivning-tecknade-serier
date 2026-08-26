# Tecknade serier sedan 2020

Index of Swedish comics & graphic novels published since 2020.

## Bidra!

Saknas en utgivning? Då kan du lägga till den själv:

**1. Klona ned repot**

**2. Skapa en yaml-fil** i `data/books/`, t.ex. `data/books/mitt-fanzin-3.yaml` (filnamnet ska vara samma som id, måste sluta på `.yaml` och vara unikt i mappen, och inte innehålla mellanslag, specialtecken eller åäö). Minsta innehåll som behövs:

```yaml
id: mitt-fanzin-3
title: Mitt Fanzin #3
authors:
  - Efternamn, Förnamn
year: 2026
hidden: false
```

Har utgivningen ett ISBN, använd det (utan bindestreck) som `id` (och filnamn) — då slås det ihop automatiskt istället för att bli en dubblett om det senare även dyker upp via någon av våra andra källor. Fler valfria fält:

```yaml
isbn: "9789180581196"
publisher: Eget förlag
description: En kort text om utgivningen.
cover_url: covers/mitt-fanzin-3.jpg
more_info_url: https://exempel.se
buy_url: https://exempel.se/kop
```

**3. Lägg till ett omslag** (valfritt): spara bildfilen i `data/covers/`, t.ex. `data/covers/mitt-fanzin-3.jpg`, och peka på den med `cover_url: covers/mitt-fanzin-3.jpg` ovan.

**4. Skicka en pull request** med den nya filen (och ev. omslagsbilden). Inget behöver köras lokalt — sajten byggs om automatiskt när ändringen är sammanslagen till `main`.
