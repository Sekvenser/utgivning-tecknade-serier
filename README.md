# Tecknade serier sedan 2020

Index of Swedish comics & graphic novels published since 2020.

## Bidra manuellt (småförlag, fansin m.m.)

Saknas en utgivning? Lägg till den själv:

**1. Skapa en yaml-fil** i `data/books/`, t.ex. `data/books/mitt-fanzin-3.yaml` (filnamnet spelar ingen roll, men måste sluta på `.yaml` och vara unikt i mappen). Minsta innehåll som behövs:

```yaml
id: mitt-fanzin-3
title: Mitt Fanzin #3
authors:
  - Förnamn Efternamn
year: 2026
hidden: false
```

Har utgivningen ett ISBN, använd det (utan bindestreck) som `id` — då slås det ihop automatiskt istället för att bli en dubblett om det senare även dyker upp via någon av våra andra källor. Fler valfria fält:

```yaml
isbn: "9789180581196"
publisher: Eget förlag
description: En kort text om utgivningen.
cover_url: covers/mitt-fanzin-3.jpg
more_info_url: https://exempel.se
buy_url: https://exempel.se/kop
```

**2. Lägg till ett omslag** (valfritt): spara bildfilen i `data/covers/`, t.ex. `data/covers/mitt-fanzin-3.jpg`, och peka på den med `cover_url: covers/mitt-fanzin-3.jpg` ovan.

**3. Skicka en pull request** med den nya filen (och ev. omslagsbilden). Inget behöver köras lokalt — sajten byggs om automatiskt när ändringen är sammanslagen till `main`.
