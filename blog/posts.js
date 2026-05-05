/* ===================================================================
   posts.js — Lista mestre de artigos publicados no blog DANFSe.tools

   Como adicionar um novo artigo:
   1. Crie o arquivo HTML do artigo (ex: meu-artigo.html) na pasta blog/
   2. Adicione um objeto neste array com os campos abaixo
   3. Faça commit no GitHub e o site atualiza automaticamente

   Campos:
   - slug:     nome do arquivo HTML sem extensão (ex: "o-que-e-danfse")
   - category: rótulo curto (ex: "Conceitos", "Operacional", "Técnico")
   - title:    título completo do artigo
   - excerpt:  resumo curto (1-2 frases)
   - readTime: tempo estimado de leitura (ex: "6 min")
   - level:    "Iniciante", "Intermediário" ou "Avançado"
   - group:    "basico" | "tecnico" | "operacional"
   =================================================================== */
window.POSTS = [
  {
    "slug": "o-que-e-danfse",
    "category": "Conceitos",
    "title": "O que é DANFSe e qual a diferença para a NFS-e",
    "excerpt": "Entenda a relação entre o documento fiscal eletrônico (NFS-e) e sua representação visual em PDF (DANFSe), e por que os dois existem.",
    "readTime": "6 min",
    "level": "Iniciante",
    "group": "basico"
  },
  {
    "slug": "converter-xml-nfse-pdf",
    "category": "Tutorial",
    "title": "Como converter XML de NFS-e em PDF",
    "excerpt": "Passo a passo completo para gerar a DANFSe (PDF) a partir do XML, em lote ou individualmente, sem instalar programas.",
    "readTime": "7 min",
    "level": "Iniciante",
    "group": "basico"
  },
  {
    "slug": "como-abrir-xml-nfse",
    "category": "Operacional",
    "title": "Como abrir um arquivo XML de NFS-e",
    "excerpt": "Métodos seguros para visualizar o conteúdo de um XML de nota fiscal de serviço, sem alterar o arquivo original.",
    "readTime": "5 min",
    "level": "Iniciante",
    "group": "basico"
  },
  {
    "slug": "nfse-nacional-vs-municipal-abrasf",
    "category": "Comparativo",
    "title": "NFS-e Padrão Nacional vs NFS-e Municipal (ABRASF)",
    "excerpt": "Diferenças de leiaute, namespace, campos, validação e migração entre os dois padrões coexistentes.",
    "readTime": "9 min",
    "level": "Intermediário",
    "group": "tecnico"
  },
  {
    "slug": "retencao-issqn-nfse",
    "category": "Tributário",
    "title": "Quando o ISSQN é retido na NFS-e e como identificar no XML",
    "excerpt": "Tipos de retenção (tomador, intermediário, prestador), código tpRetISSQN no XML, e responsabilidade tributária.",
    "readTime": "8 min",
    "level": "Intermediário",
    "group": "tecnico"
  },
  {
    "slug": "nfse-nacional-mei",
    "category": "MEI",
    "title": "NFS-e Nacional para MEI: como funciona",
    "excerpt": "Obrigatoriedade, emissão pelo portal nacional, isenção de ISS e cuidados específicos do Microempreendedor Individual.",
    "readTime": "6 min",
    "level": "Iniciante",
    "group": "operacional"
  }
];
