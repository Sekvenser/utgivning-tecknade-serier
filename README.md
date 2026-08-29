# Tecknade serier sedan 2020

Index of Swedish comics, graphic novels and related publications, published since 2020.

## Bidra!

Saknas en utgivning? Då kan du lägga till den själv:

**1. Klona ned repot** Skapa en fork och klona ned.

**2. Skapa en yaml-fil** i `data/books/`, t.ex. `data/books/mitt-fanzin-3.yaml` (filnamnet ska vara samma som id, måste sluta på `.yaml` och vara unikt i mappen, och inte innehålla mellanslag, specialtecken eller åäö). Minsta innehåll som behövs:

```yaml
id: mitt-fanzin-3
title: "Mitt Fanzin #3"
authors:
  - Efternamn, Förnamn
year: 2026
hidden: false
```

Har utgivningen ett ISBN, använd det (utan bindestreck) som `id` (och filnamn) — då slås det ihop automatiskt istället för att bli en dubblett om det senare även dyker upp via någon av våra andra källor. Fler valfria fält:

```yaml
isbn: "9789180581196"
publisher: Eget förlag
description: "En kort text om utgivningen."
cover_url: covers/9789180581196.jpg
more_info_url: https://exempel.se
buy_url: https://exempel.se/kop
```

Om det inte finns en webbplats att köpa ifrån, och det fortfarande går att köpa utgåvan, lägg in i beskrivningstexten (description) hur man gör.

**3. Lägg till ett omslag** (valfritt): spara bildfilen i `data/covers/`, t.ex. `data/covers/mitt-fanzin-3.jpg`. Kör sedan `python3 cli.py optimize-covers data/covers/mitt-fanzin-3.jpg` för att konvertera den till `.webp` (mindre filstorlek), och peka på den nya filen med `cover_url: covers/mitt-fanzin-3.webp` ovan.

**4. Skicka en pull request** med den nya filen (och ev. omslagsbilden).

Du kan även skapa en [issue](https://github.com/Sekvenser/utgivning-tecknade-serier/issues), och lägga in informationen som du vill ha med, om du känner dig osäker på hur man använder git.
